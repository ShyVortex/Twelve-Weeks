// Offline harness for tools/ext/loadjson.c: the REAL loadjson.c is #included, the engine / loadout reads are stubbed.
// Driven by tools/tests/test_loadjson_c.py.   Build: gcc -std=gnu2x -O1 -g -o loadjson_test loadjson_test.c   (windows.h: mingw)
//   loadjson_test export <dir> <active_kind> <active_i> <n_populated> <id>...   writes <dir>\t2r-loadout.json (lj_export(1)); every table lists <id>...
//   loadjson_test import <dir> <file>                                              runs lj_import on <file> copied to <dir>\t2r-loadout-launcher.json, prints the resulting loadouts
//   loadjson_test fuzz <dir> <seed-file> <iterations> <rng-seed>                  hostile / garbled / oversized launcher files through lj_parse + lj_import
//   loadjson_test state <dir>                                                      prints g_lj_applied as lj_state_load reads it from <dir>\t2r-loadout.json
// Exit 0 = ran; the fuzz run exits 3 if something the game would not accept was applied.
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>
#include <stddef.h>
#include "../skills.h"

#define VMA(x) ((uintptr_t)g_winmm + ((x) - 0x180000000ULL))
#define N_CUSTOM 6
#define N_CLASSES 8
static uint8_t *g_winmm;
static const uint8_t *g_large_tab;                 // NULL: the large table is the engine's at VMA(0x1800A0DB0)
static char g_loadout_path[MAX_PATH];
typedef struct { uint32_t w[3]; uint64_t k[3]; } loadout_t;
static loadout_t g_lo[N_CUSTOM];
static uint64_t g_sk4[N_CUSTOM];
enum { LO_NONE };
static int g_lo_active, g_lo_state, g_lo_pending, g_in_match;
static struct { int ok; } g_lo_snap;
static struct { int nlv; } SK[SK_COUNT];
static uint8_t g_small[24][0x38], g_purch[24][0x40];

static void xlog(const char *fmt, ...) { (void)fmt; }
static void msg_hook(const char *t, float s, int f, uint64_t id) { (void)t; (void)s; (void)f; (void)id; }
static DWORD fa_poll(const char *p) { return GetFileAttributesA(p); }
static uint8_t match_substate(void) { return g_in_match ? 6 : 0; }
static int gl_pick_refused(int row) { return row == 5; }
static uint8_t *weapon_row(int slot, uint32_t i) { (void)slot; return g_small[i]; }
static uint8_t *lo_purch_tab(void) { return &g_purch[0][0]; }
static int sk_id(uint64_t v) { int id = (int)((v >> 40) & 0xff); return (v & SK_TAG) && id > 0 && id < SK_COUNT ? id : 0; }
static int sk_lv(uint64_t v) { int id = sk_id(v), lv = (int)((v >> 36) & 0xf); return id && lv >= 1 && lv <= SK[id].nlv ? lv : 0; }
static uint64_t sk_norm(uint64_t v) { return sk_lv(v) ? v : 0; }
static uint64_t *sk4_slot(const loadout_t *l) { return &g_sk4[l - g_lo]; }
static int lo_cost(const loadout_t *l) {            // stand-in rule (the real one reads the engine tables): 2 LP per gun, 1 per skill level
    int c = 0;
    for (int i = 0; i < 3; i++) if (l->w[i] != 0xffffffffu) c += 2;
    for (int i = 0; i < 3; i++) c += sk_lv(sk_norm(l->k[i]));
    return c + sk_lv(sk_norm(*sk4_slot(l)));
}
static int lo_valid(const loadout_t *l) { return lo_cost(l) <= 13; }
static uint32_t lo_class_row(int slot, const char *spec) {
    const uint32_t *cnt = (const uint32_t *)VMA(0x1800A0DA4);
    for (uint32_t i = 0; i < cnt[slot]; i++) {
        const uint8_t *row = slot == 2 ? lo_purch_tab() + i * 0x40 : slot == 0 && !g_large_tab ? (const uint8_t *)VMA(0x1800A0DB0) + i * 0x38 : weapon_row(slot, i);
        const char *id = *(const char **)(row + 0x10);
        if (id && !strcmp(id, spec)) return i;
    }
    return 0xffffffffu;
}
static const loadout_t *lo_of(int idx) { return &g_lo[idx % N_CUSTOM]; }
static void lo_write_obj(const loadout_t *l) { (void)l; }
static void lo_save(void) {}
static void sk4_save(void) {}
#include "../loadjson.c"

static char *g_tab[3][24]; static int g_ntab[3];         // engine slot -> ids (0 large, 1 small, 2 purchasable)
static char *g_std_tab[3][6] = {
    { "rifle-mpx5", "shotgun-shorty", "bow-ellie", "shotgun-baserri-over-under", "rifle-mpx5", "rifle-mpx5" },
    { "pistol-beretta", "pistol-beretta-supp", "pistol-beretta", "pistol-beretta", "pistol-beretta", "pistol-beretta" },
    { "shotgun-shorty", "bow-ellie", "shotgun-shorty", "shotgun-shorty", "shotgun-shorty", "shotgun-shorty" } };
static void set_tables(void) {
    uint32_t *cnt = (uint32_t *)VMA(0x1800A0DA4);
    for (int s = 0; s < 3; s++) {
        cnt[s] = (uint32_t)g_ntab[s];
        for (int i = 0; i < g_ntab[s]; i++) {
            uint8_t *row = s == 0 ? (uint8_t *)VMA(0x1800A0DB0) + i * 0x38 : s == 1 ? g_small[i] : g_purch[i];
            *(const char **)(row + 0x10) = g_tab[s][i];
        }
    }
}
static void std_tables(void) { for (int s = 0; s < 3; s++) { g_ntab[s] = 6; memcpy(g_tab[s], g_std_tab[s], sizeof g_std_tab[s]); } }
static void load_tables(const char *file) {              // lines "<slot> <id>", ids kept byte for byte (no escapes); at most 24 per slot
    static char data[65536];
    FILE *f = fopen(file, "rb"); size_t n = f ? fread(data, 1, sizeof data - 1, f) : 0; if (f) fclose(f);
    data[n] = 0;
    for (char *l = strtok(data, "\n"); l; l = strtok(NULL, "\n")) {
        int s = l[0] - '0';
        if (s >= 0 && s < 3 && l[1] == ' ' && g_ntab[s] < 24) g_tab[s][g_ntab[s]++] = l + 2;
    }
}
static void init_common(const char *dir) {
    g_winmm = calloc(1, 0x200000);
    snprintf(g_loadout_path, sizeof g_loadout_path, "%s\\x", dir);
    for (int i = 1; i < SK_COUNT; i++) SK[i].nlv = i == SK_LETHAL ? 2 : 3;
}
static void print_state(void) {
    printf("active %d\n", g_lo_active);
    for (int i = 0; i < N_CUSTOM; i++) {
        const loadout_t *l = &g_lo[i];
        printf("c%d %d %d %d %llx %llx %llx %llx\n", i, (int)l->w[1], (int)l->w[0], (int)l->w[2], (unsigned long long)l->k[0], (unsigned long long)l->k[1], (unsigned long long)l->k[2], (unsigned long long)g_sk4[i]);
    }
}
static unsigned long long rs;
static unsigned rnd(void) { rs = rs * 6364136223846793005ULL + 1442695040888963407ULL; return (unsigned)(rs >> 33); }

int main(int argc, char **argv) {
    if (argc < 3) return 2;
    init_common(argv[2]);
    if (!strcmp(argv[1], "export") && argc >= 7) {
        g_lo_active = !strcmp(argv[3], "custom") ? atoi(argv[4]) : N_CUSTOM + atoi(argv[4]);
        int np = atoi(argv[5]);
        load_tables(argv[6]);
        set_tables();
        for (int i = 0; i < N_CUSTOM; i++) {
            loadout_t *l = &g_lo[i];
            l->w[0] = l->w[1] = l->w[2] = 0xffffffffu;
            if (i >= np) continue;                                     // an empty slot: no guns, no skills
            if (g_ntab[1]) l->w[1] = (uint32_t)(i % g_ntab[1]);
            if (g_ntab[0]) l->w[0] = (uint32_t)((i * 5 + 1) % g_ntab[0]);
            if (g_ntab[2] && i % 3 != 2) l->w[2] = (uint32_t)((i * 7 + 2) % g_ntab[2]);
            for (int j = 0; j < 3; j++) l->k[j] = SK_V(1 + (i * 4 + j) % (SK_COUNT - 1), 1 + (i + j) % 2);
            g_sk4[i] = SK_V(1 + (i * 4 + 3) % (SK_COUNT - 1), 1 + i % 2);
        }
        lj_state_load();
        g_lj_applied = 1234567890123LL;
        lj_export(1);
        return 0;
    }
    if (!strcmp(argv[1], "state")) {
        lj_state_load();
        printf("%lld\n", g_lj_applied);
        return 0;
    }
    if (!strcmp(argv[1], "import") && argc >= 4) {
        std_tables(); set_tables();
        for (int i = 0; i < N_CUSTOM; i++) { g_lo[i].w[0] = g_lo[i].w[2] = 0xffffffffu; g_lo[i].w[1] = 0; }
        char p[MAX_PATH]; lj_path(p, sizeof p, "t2r-loadout-launcher.json");
        CopyFileA(argv[3], p, FALSE);
        g_lj_applied = 0;
        int r = lj_import();
        printf("applied %d\n", r);
        print_state();
        return 0;
    }
    if (!strcmp(argv[1], "fuzz") && argc >= 6) {
        std_tables(); set_tables();
        static char seed[16384];
        FILE *f = fopen(argv[3], "rb"); size_t sn = f ? fread(seed, 1, sizeof seed - 1, f) : 0; if (f) fclose(f);
        int iters = atoi(argv[4]); rs = strtoull(argv[5], 0, 10);
        static char big[200000];
        char p[MAX_PATH]; lj_path(p, sizeof p, "t2r-loadout-launcher.json");
        static const char *junk[] = { "{", "}", "[", "]", "\"", "\\", "\\u", "\\u12", ",", ":", "null", "true", "1e999", "-0", "nan", "inf", "0x7fffffff", "\"id\"", "\"custom\"", "\"rev\":9", "\"skills\"", "{\"a\":", "[[[[[[[[[[", "\xff\xfe", "\\\"" };
        unsigned long long t = 133000000000000000ULL; int applied = 0, parsed = 0;
        for (int it = 0; it < iters; it++) {
            size_t n = 0;
            int mode = (int)(rnd() % 9);
            if (mode == 8) {                                   // oversize / pool exhaustion / depth / giant strings
                int k = (int)(rnd() % 4);
                if (k == 0) { n = (size_t)snprintf(big, sizeof big, "{\"rev\":5,\"custom\":["); for (int i = 0; i < 5000 && n < sizeof big - 40; i++) n += (size_t)snprintf(big + n, sizeof big - n, "{\"small\":{\"id\":\"a\"}},"); n += (size_t)snprintf(big + n, sizeof big - n, "1]}"); }
                else if (k == 1) { n = (size_t)snprintf(big, sizeof big, "{\"rev\":5,\"custom\":[{\"small\":{\"id\":\""); memset(big + n, 'A', 150000); n += 150000; n += (size_t)snprintf(big + n, sizeof big - n, "\"}}]}"); }
                else if (k == 2) { for (int i = 0; i < 20000; i++) big[n++] = '['; n += (size_t)snprintf(big + n, sizeof big - n, "{\"rev\":5}"); }
                else { n = (size_t)snprintf(big, sizeof big, "{\"rev\":5,\"custom\":[{\"small\":{\"id\":\"pistol-beretta"); for (int i = 0; i < 30000; i++) n += (size_t)snprintf(big + n, sizeof big - n, "\\u00"); }
            } else {
                memcpy(big, seed, sn); n = sn;
                int muts = 1 + (int)(rnd() % 8);
                for (int m = 0; m < muts; m++) {
                    size_t at = n ? rnd() % n : 0;
                    switch (mode) {
                    case 0: if (n) n = at; break;                                         // truncate
                    case 1: if (n) big[at] = (char)rnd(); break;                         // byte flip
                    case 2: { const char *j = junk[rnd() % (sizeof junk / sizeof *junk)]; size_t L = strlen(j); if (n + L < sizeof big) { memmove(big + at + L, big + at, n - at); memcpy(big + at, j, L); n += L; } break; }
                    case 3: if (n > 4) { size_t L = rnd() % 20; if (at + L > n) L = n - at; memmove(big + at, big + at + L, n - at - L); n -= L; } break;   // delete a span
                    case 4: for (size_t i = 0; i < 40 && n; i++) big[rnd() % n] = "{}[],:\"\\ 0"[rnd() % 11]; break;
                    case 5: if (n < 100000) { memcpy(big + n, seed, sn); n += sn; } break;   // doubled
                    case 6: for (size_t i = 0; i + 4 < n; i++) if (!memcmp(big + i, "\"lv\"", 4) && rnd() % 2) { memcpy(big + i + 4, ":99", 3); break; } break;
                    case 7: if (n) memset(big + at, 'x', rnd() % (n - at + 1)); break;
                    }
                }
            }
            if (n >= sizeof big) n = sizeof big - 1;
            big[n] = 0;
            {   // the reader alone, any size, on a buffer that ends exactly before a no-access page (a read or write past the NUL faults the run)
                size_t body = (n + 1 + 4095) & ~(size_t)4095;
                char *reg = VirtualAlloc(NULL, body + 4096, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE), *copy = reg + body - (n + 1);
                DWORD old;
                VirtualProtect(reg + body, 4096, PAGE_NOACCESS, &old);
                memcpy(copy, big, n + 1);
                lj_n *r = lj_parse(copy);
                parsed += r != NULL;
                VirtualFree(reg, 0, MEM_RELEASE);
            }
            f = fopen(p, "wb"); fwrite(big, 1, n, f); fclose(f);   // the real path: whole-file read (16 KB cap), gate, parse, apply
            HANDLE h = CreateFileA(p, FILE_WRITE_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE, 0, OPEN_EXISTING, 0, 0);
            if (h != INVALID_HANDLE_VALUE) { t += 10000000ULL; FILETIME ft = { (DWORD)t, (DWORD)(t >> 32) }; SetFileTime(h, 0, 0, &ft); CloseHandle(h); }
            g_lj_applied = 0; g_in_match = (int)(rnd() % 2);
            for (int i = 0; i < N_CUSTOM; i++) { g_lo[i].w[0] = g_lo[i].w[2] = 0xffffffffu; g_lo[i].w[1] = 0; memset(g_lo[i].k, 0, sizeof g_lo[i].k); g_sk4[i] = 0; }
            applied += lj_import();
            for (int i = 0; i < N_CUSTOM; i++) {                // whatever was applied is a loadout the game accepts
                const loadout_t *l = &g_lo[i];
                for (int s = 0; s < 3; s++) if (l->w[s] != 0xffffffffu && l->w[s] >= 6u) { printf("BAD row %u\n", l->w[s]); return 3; }
                if (lo_cost(l) > 13) { printf("BAD cost %d\n", lo_cost(l)); return 3; }
                for (int s = 0; s < 3; s++) if (l->k[s] && !sk_lv(l->k[s])) { printf("BAD skill %llx\n", (unsigned long long)l->k[s]); return 3; }
            }
            if (g_lo_active < 0 || g_lo_active >= N_CUSTOM + N_CLASSES) { printf("BAD active %d\n", g_lo_active); return 3; }
            g_lo_active = 0;
        }
        printf("fuzz ok %d iterations, %d parsed, %d applied\n", iters, parsed, applied);
        return 0;
    }
    return 2;
}
