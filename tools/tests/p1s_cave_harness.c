// Offline harness: RUNS the winmm side-file cave (tools/features/p1_side_map.py) in a fake image at 0x180000000.
//   gcc -std=gnu2x -O1 -o p1s_cave_harness.exe p1s_cave_harness.c      (MSYS2 UCRT64; the process must be able to reserve 0x180000000..0x180400000)
//   p1s_cave_harness.exe <section.bin> <section VA hex> <entry VA hex> <dir> <size1> <FO> <size2>
// <dir>\fake.dll = the "winmm.dll" (payload bytes at FO..FO+size1), <dir>\t2r-maps\part1\part1.dat = the side file (may be absent / wrong size).
// Fake image: IAT slots 0x180129xxx point at the real kernel32 functions except GetModuleFileNameW (returns <dir>\fake.dll), the loader globals
// 0x1801398d0/d8/e8 are set like the loader leaves them, the resume / fail targets are tiny stubs. Prints
//   RESULT status=<n> layout=<n> step=<n> err=<hex> ret=<1 resumed | 0 fail branch> d8=<size>
//   MEM full-ok | MEM view1-ok-hole-reserved | MEM view1-ok-hole-other | MEM d0-unchanged | MEM BAD <what>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static char g_dir[MAX_PATH];

static DWORD WINAPI fake_gmfn(HMODULE m, LPWSTR buf, DWORD n) {
    (void)m;
    char p[MAX_PATH];
    snprintf(p, sizeof p, "%s\\fake.dll", g_dir);
    return (DWORD)MultiByteToWideChar(CP_ACP, 0, p, -1, buf, (int)n) - 1;
}
static void put64(uint64_t va, uint64_t v) { *(uint64_t *)(uintptr_t)va = v; }
static uint64_t get64(uint64_t va) { return *(uint64_t *)(uintptr_t)va; }
static uint8_t *slurp(const char *path, size_t *n) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); *n = (size_t)ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *b = (uint8_t *)malloc(*n ? *n : 1);
    if (fread(b, 1, *n, f) != *n) { fclose(f); free(b); return NULL; }
    fclose(f);
    return b;
}

int main(int argc, char **argv) {
    if (argc < 8) return 2;
    uint64_t secva = strtoull(argv[2], NULL, 16), entry = strtoull(argv[3], NULL, 16);
    snprintf(g_dir, sizeof g_dir, "%s", argv[4]);
    uint64_t size1 = strtoull(argv[5], NULL, 10), fo = strtoull(argv[6], NULL, 10), size2 = strtoull(argv[7], NULL, 10);
    uint8_t *img = (uint8_t *)VirtualAlloc((void *)0x180000000ULL, 0x200000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (img != (uint8_t *)0x180000000ULL) { printf("NOIMAGE %p\n", img); return 3; }
    size_t sn = 0;
    uint8_t *sec = slurp(argv[1], &sn);
    if (!sec) return 4;
    if (secva >= 0x180200000ULL && VirtualAlloc((void *)(uintptr_t)(secva & ~0xFFFFULL), ((secva & 0xFFFF) + sn + 0xFFFF) & ~(size_t)0xFFFF, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE) != (void *)(uintptr_t)(secva & ~0xFFFFULL)) { printf("NOSECTION\n"); return 5; }
    memcpy((void *)(uintptr_t)secva, sec, sn);
    HMODULE k = GetModuleHandleW(L"kernel32.dll");
    put64(0x180129520, (uint64_t)(uintptr_t)GetProcAddress(k, "CreateFileW"));
    put64(0x180129508, (uint64_t)(uintptr_t)GetProcAddress(k, "CloseHandle"));
    put64(0x180129648, (uint64_t)(uintptr_t)GetProcAddress(k, "GetFileSizeEx"));
    put64(0x180129658, (uint64_t)(uintptr_t)GetProcAddress(k, "GetLastError"));
    put64(0x180129668, (uint64_t)(uintptr_t)fake_gmfn);
    put64(0x180129680, (uint64_t)(uintptr_t)GetProcAddress(k, "GetModuleHandleW"));
    put64(0x180129690, (uint64_t)(uintptr_t)GetProcAddress(k, "GetProcAddress"));
    put64(0x1801298B8, (uint64_t)(uintptr_t)GetProcAddress(k, "VirtualAlloc"));
    put64(0x1801298C0, (uint64_t)(uintptr_t)GetProcAddress(k, "VirtualFree"));
    uint8_t *blob = (uint8_t *)malloc(size1 + 1);                 // stands for the blob inside the image (layout 2 keeps this pointer)
    memset(blob, 0x5a, size1);
    put64(0x1801398D0, (uint64_t)(uintptr_t)blob);
    put64(0x1801398D8, size1);
    put64(0x1801398E8, fo);
    // thunk @0x180001000: sub rsp,8 ; xor eax,eax (ZF=1: the loader's jne is not taken) ; jmp entry
    uint8_t *t = (uint8_t *)0x180001000ULL;
    uint8_t th[] = {0x48, 0x83, 0xEC, 0x08, 0x31, 0xC0, 0xE9, 0, 0, 0, 0};
    int32_t rel = (int32_t)(entry - (0x180001000ULL + 11));
    memcpy(th + 7, &rel, 4);
    memcpy(t, th, sizeof th);
    uint8_t res[] = {0x48, 0x83, 0xC4, 0x08, 0xB8, 1, 0, 0, 0, 0xC3};      // 0x1800019a6: resumed -> return 1
    memcpy((void *)0x1800019A6ULL, res, sizeof res);
    uint8_t fail[] = {0x48, 0x83, 0xC4, 0x08, 0x31, 0xC0, 0xC3};            // 0x180001adb: the loader's failure exit -> return 0
    memcpy((void *)0x180001ADBULL, fail, sizeof fail);
    int ret = ((int (*)(void))t)();
    uint32_t *d = (uint32_t *)(uintptr_t)secva;
    uint64_t d0 = get64(0x1801398D0), d8 = get64(0x1801398D8);
    printf("RESULT status=%u layout=%u step=%u err=%x ret=%d d8=%llu\n", d[2], d[3], d[4], d[5], ret, (unsigned long long)d8);
    if (argc > 8 && d[3] == 3) { FILE *o = fopen(argv[8], "wb"); fwrite((void *)(uintptr_t)d0, 1, (size_t)d8, o); fclose(o); }
    char p[MAX_PATH];
    snprintf(p, sizeof p, "%s\\fake.dll", g_dir);
    size_t dn = 0;
    uint8_t *dll = slurp(p, &dn);
    snprintf(p, sizeof p, "%s\\t2r-maps\\part1\\part1.dat", g_dir);
    size_t pn = 0;
    uint8_t *side = slurp(p, &pn);
    if (d[3] == 2) { printf(d0 == (uint64_t)(uintptr_t)blob ? "MEM d0-unchanged\n" : "MEM BAD d0-moved\n"); return 0; }
    if (!dll || fo + size1 > dn) { printf("MEM BAD no-dll\n"); return 0; }
    if (memcmp((void *)(uintptr_t)d0, dll + fo, (size_t)size1)) { printf("MEM BAD view1-content\n"); return 0; }
    if (d[3] == 3) {
        if (!side || pn != size2 + 16 || memcmp((void *)(uintptr_t)(d0 + size1), side, (size_t)size2)) printf("MEM BAD view2-content\n");
        else printf("MEM full-ok\n");
    } else {
        MEMORY_BASIC_INFORMATION mbi;
        uint64_t hole = (d0 - (fo & 0xFFFF)) + (fo & 0xFFFF) + size1;       // = d0 + size1, 64 KiB aligned by construction
        VirtualQuery((void *)(uintptr_t)hole, &mbi, sizeof mbi);
        printf(mbi.State == MEM_RESERVE ? "MEM view1-ok-hole-reserved\n" : "MEM view1-ok-hole-other state=%lx\n", (unsigned long)mbi.State);
    }
    return 0;
}
