// Offline harness for tools/ext/crashbin.h (the crash handler's t2r-crash-<pid>-1.bin writer).
//   gcc -std=gnu2x -O2 -o crashbin_harness.exe crashbin_harness.c        (MSYS2 UCRT64)
//   crashbin_harness.exe <scratch dir>   makes 5 old t2r-crash-*.bin (ages 1..5 h), runs cb_init (keeps the 2 newest), fills a g_cdiag + fake rings,
//   calls cb_write twice with a fake exception record (the second call must write nothing) and prints "HARNESS OK pid <pid>".
// tools/tests/test_crashdiag.py parses the written file with tools/reports/cdiag_rings.py.
#include <stdio.h>
#include <stdlib.h>
#include "../ext/crashdiag.h"
#include "../ext/crashbin.h"

#define DCR_N 512
static struct { uint64_t frame, sid, a0; uint32_t tid, ms; } g_dcr[DCR_N];
static char g_xring[512][220];
static int g_fails;
static volatile int32_t g_dcr_i, g_xring_i;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); g_fails++; } } while (0)

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    wchar_t dir[MAX_PATH]; MultiByteToWideChar(CP_UTF8, 0, argv[1], -1, dir, MAX_PATH);
    size_t dl = wcslen(dir); if (dir[dl - 1] != L'\\') { dir[dl++] = L'\\'; dir[dl] = 0; }
    ULARGE_INTEGER now; FILETIME ft; GetSystemTimeAsFileTime(&ft); now.LowPart = ft.dwLowDateTime; now.HighPart = ft.dwHighDateTime;
    for (int i = 1; i <= 5; i++) {
        wchar_t p[MAX_PATH]; swprintf(p, MAX_PATH, L"%lst2r-crash-%d-1.bin", dir, 1000 + i);
        HANDLE h = CreateFileW(p, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        CHECK(h != INVALID_HANDLE_VALUE);
        DWORD w; WriteFile(h, "old", 3, &w, NULL);
        ULARGE_INTEGER t; t.QuadPart = now.QuadPart - (uint64_t)i * 3600ULL * 10000000ULL; FILETIME f = {t.LowPart, t.HighPart};
        SetFileTime(h, NULL, NULL, &f); CloseHandle(h);
    }
    {   wchar_t p[MAX_PATH]; swprintf(p, MAX_PATH, L"%lst2r-crash-notes.txt", dir);       // not a crash file: untouched
        HANDLE h = CreateFileW(p, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL); if (h != INVALID_HANDLE_VALUE) CloseHandle(h); }
    cb_write(1, 2, 3, 4, 5, 6, &g_cdiag, sizeof g_cdiag, g_dcr, sizeof g_dcr, 0, &g_xring[0][0], 512, 220, 0);          // before cb_init: must write nothing
    cb_init(dir, "Oct 19 2026 12:34:56 (release)");
    CHECK(g_cb_ok);
    g_cdiag.self = (uint64_t)&g_cdiag; g_cdiag.exe_base = 0x140000000ULL; g_cdiag.ext_base = 0x7ff800000000ULL;
    g_cdiag.dcr_addr = (uint64_t)g_dcr; g_cdiag.dcr_n = DCR_N; g_cdiag.dcr_stride = sizeof g_dcr[0];
    g_cdiag.xr_addr = (uint64_t)g_xring; g_cdiag.xr_n = 512; g_cdiag.xr_w = 220;
    g_cdiag.dcr_i_addr = (uint64_t)&g_dcr_i; g_cdiag.xr_i_addr = (uint64_t)&g_xring_i;       // (the reader takes the indexes from the file header, not from these)
    for (uint32_t i = 1; i <= 140; i++) cd_be_note(1000 + i, 5000 + i, 7, 0x1111, 0xA000 + i, i);
    EXCEPTION_RECORD er = {0}; er.ExceptionCode = EXCEPTION_ACCESS_VIOLATION; er.ExceptionAddress = (void *)0x1415f52b0ULL;
    er.NumberParameters = 2; er.ExceptionInformation[0] = 0; er.ExceptionInformation[1] = 0x1f0;
    for (int i = 1; i <= 600; i++) { g_dcr[i & (DCR_N - 1)].frame = 9000 + i; g_dcr[i & (DCR_N - 1)].sid = 0x1111; g_dcr[i & (DCR_N - 1)].a0 = 0xB000 + i; g_dcr[i & (DCR_N - 1)].tid = 7; g_dcr[i & (DCR_N - 1)].ms = 100 + i; }
    int dcr_i = 600, xi = 700;
    for (int i = 1; i <= xi; i++) snprintf(g_xring[i & 511], 220, "log line %d", i);
    cb_write(er.ExceptionCode, (uint64_t)er.ExceptionAddress, er.ExceptionInformation[0], er.ExceptionInformation[1], 77, 4321, &g_cdiag, sizeof g_cdiag, g_dcr, sizeof g_dcr, dcr_i, &g_xring[0][0], 512, 220, xi);
    cb_write(er.ExceptionCode, 0xdead, 0, 0, 78, 1, &g_cdiag, sizeof g_cdiag, g_dcr, sizeof g_dcr, dcr_i, &g_xring[0][0], 512, 220, xi);        // one shot: ignored
    printf("HARNESS %s pid %lu\n", g_fails ? "FAILED" : "OK", (unsigned long)GetCurrentProcessId());
    return g_fails ? 1 : 0;
}
