// Offline harness for tools/ext/crashfilter.h (when the ext's crash report runs) + crashbin.h (the one-shot evidence file); re/crash-veh-filter-1019.md.
//   gcc -std=gnu2x -O2 -o crashfilter_harness.exe crashfilter_harness.c        (MSYS2 UCRT64)
//   crashfilter_harness.exe <scratch dir>   in-process: handled exceptions (IsBadReadPtr probes, an AV another vectored handler continues, debug-print codes, a flood of
//   handled AVs) must produce no report and no evidence file; then spawns itself as a child that raises a real unhandled access violation and checks that the
//   evidence file for that pid exists, the report ran exactly once, and the filter installed BEFORE ours (the "game's dump writer") was called and its value used.
//   Child scenario 2: the "game" replaces the top-level filter after our init; a handled candidate re-arms us and the new filter is the one chained.
#include <stdio.h>
#include <stdlib.h>
#include "../ext/crashfilter.h"
#include "../ext/crashbin.h"

static int g_fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); g_fails++; } } while (0)

static volatile LONG g_reports, g_notes;
static uint8_t g_blk[64]; static uint8_t g_dcr[64]; static char g_xr[8][16];
static wchar_t g_dir[MAX_PATH];
static char g_dirA[MAX_PATH];

static void on_report(EXCEPTION_POINTERS *ep) {
    InterlockedIncrement(&g_reports);
    cb_write(ep->ExceptionRecord->ExceptionCode, (uint64_t)ep->ExceptionRecord->ExceptionAddress, 0, 0, GetCurrentThreadId(), 1, g_blk, sizeof g_blk, g_dcr, sizeof g_dcr, 0, &g_xr[0][0], 8, 16, 3);
}
static void on_note(EXCEPTION_POINTERS *ep) { (void)ep; InterlockedIncrement(&g_notes); }

static LONG CALLBACK cont_veh(EXCEPTION_POINTERS *ep) {
    if (ep->ExceptionRecord->ExceptionCode == 0x406D1388 || ep->ExceptionRecord->ExceptionCode == 0x40010006) return EXCEPTION_CONTINUE_EXECUTION;   // (a debugger / the engine's SEH block would swallow these)         // "someone else handles it": a vectored handler that continues the 0x7357-tagged AVs
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && ep->ExceptionRecord->NumberParameters >= 1 && ep->ExceptionRecord->ExceptionInformation[0] == 0x7357)
        return EXCEPTION_CONTINUE_EXECUTION;
    return EXCEPTION_CONTINUE_SEARCH;
}
typedef void (NTAPI *rtl_raise_fn)(PEXCEPTION_RECORD);
static void raise_handled_av(void) {
    EXCEPTION_RECORD er; memset(&er, 0, sizeof er);
    er.ExceptionCode = EXCEPTION_ACCESS_VIOLATION; er.NumberParameters = 2; er.ExceptionInformation[0] = 0x7357;
    ((rtl_raise_fn)GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "RtlRaiseException"))(&er);      // continuable; sets ExceptionAddress = our call site
}

static void marker(const char *name, const char *text) {
    char p[MAX_PATH + 64]; snprintf(p, sizeof p, "%s\\%s", g_dirA, name);
    HANDLE h = CreateFileA(p, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD w; WriteFile(h, text, (DWORD)strlen(text), &w, NULL); CloseHandle(h);
}
static LONG WINAPI game_filter_a(EXCEPTION_POINTERS *ep) { (void)ep; char b[64]; snprintf(b, sizeof b, "reports=%ld", (long)g_reports); marker("prev-A.txt", b); return EXCEPTION_EXECUTE_HANDLER; }
static LONG WINAPI game_filter_b(EXCEPTION_POINTERS *ep) { (void)ep; char b[64]; snprintf(b, sizeof b, "reports=%ld", (long)g_reports); marker("prev-B.txt", b); return EXCEPTION_EXECUTE_HANDLER; }

static int file_exists_pid(DWORD pid) {
    wchar_t p[MAX_PATH + 64]; swprintf(p, MAX_PATH + 64, L"%lst2r-crash-%lu-1.bin", g_dir, (unsigned long)pid);
    return GetFileAttributesW(p) != INVALID_FILE_ATTRIBUTES;
}

static int child(int scenario) {
    cb_init(g_dir, "Oct 19 2026 12:34:56 (release)");
    AddVectoredExceptionHandler(1, cf_veh);
    AddVectoredExceptionHandler(0, cont_veh);
    if (scenario == 1) SetUnhandledExceptionFilter(game_filter_a);      // the game's filter exists before the ext loads
    cf_init(on_report, on_note);
    for (int i = 0; i < 3; i++) raise_handled_av();                      // handled noise first: must not consume the one shot
    if (scenario == 3) { SetUnhandledExceptionFilter((LPTOP_LEVEL_EXCEPTION_FILTER)(uintptr_t)0x10000); cf_arm(); }      // stale prev pointer (unmapped): chaining must not fault
    if (scenario == 2) { SetUnhandledExceptionFilter(game_filter_b); raise_handled_av(); }      // the game replaces us; the next candidate re-arms and chains B
    *(volatile int *)0 = 1;                                              // the real crash
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    MultiByteToWideChar(CP_UTF8, 0, argv[1], -1, g_dir, MAX_PATH);
    size_t dl = wcslen(g_dir); if (g_dir[dl - 1] != L'\\') { g_dir[dl++] = L'\\'; g_dir[dl] = 0; }
    snprintf(g_dirA, sizeof g_dirA, "%s", argv[1]); { size_t n = strlen(g_dirA); if (n && (g_dirA[n - 1] == '\\' || g_dirA[n - 1] == '/')) g_dirA[n - 1] = 0; }
    if (argc >= 4 && !strcmp(argv[2], "child")) return child(atoi(argv[3]));

    // ---- classification (pure)
    EXCEPTION_RECORD er; EXCEPTION_POINTERS ep = {&er, NULL};
    memset(&er, 0, sizeof er);
    er.ExceptionCode = EXCEPTION_ACCESS_VIOLATION; er.ExceptionAddress = (void *)GetProcAddress(GetModuleHandleW(L"kernelbase.dll"), "Sleep");
    CHECK(cf_classify(&ep) == 0);                       // IsBadReadPtr-style AV inside kernelbase
    er.ExceptionAddress = (void *)&child; CHECK(cf_classify(&ep) == 1);                         // AV in our / the game's code: candidate only
    er.ExceptionCode = EXCEPTION_BREAKPOINT; CHECK(cf_classify(&ep) == 2);                        // int3 in the exe module: engine assert, reported at once
    er.ExceptionAddress = (void *)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "Sleep"); CHECK(cf_classify(&ep) == 0);   // foreign int3
    er.ExceptionCode = EXCEPTION_STACK_OVERFLOW; CHECK(cf_classify(&ep) == 2);
    er.ExceptionCode = 0x406D1388; CHECK(cf_classify(&ep) == 0);
    er.ExceptionCode = 0x40010006; CHECK(cf_classify(&ep) == 0);
    er.ExceptionCode = 0xE06D7363; CHECK(cf_classify(&ep) == 0);                                 // C++ throw: never a first-chance candidate (a last-chance report is still made)

    // ---- handled exceptions in this process: no report, no evidence
    cb_init(g_dir, "Oct 19 2026 12:34:56 (release)");
    AddVectoredExceptionHandler(1, cf_veh);
    AddVectoredExceptionHandler(0, cont_veh);
    cf_init(on_report, on_note);
    for (int i = 0; i < 5; i++) { CHECK(IsBadReadPtr((void *)8, 4)); CHECK(IsBadWritePtr((void *)8, 4)); }
    CHECK(g_notes == 0 && g_reports == 0);              // kernelbase AVs filtered at the root
    RaiseException(0x406D1388, 0, 0, NULL); RaiseException(0x40010006, 0, 0, NULL);
    CHECK(g_notes == 0 && g_reports == 0);
    raise_handled_av();
    CHECK(g_notes == 1 && g_reports == 0);              // candidate noted, handled by another handler: still no report
    for (int i = 0; i < 40; i++) raise_handled_av();
    CHECK(g_notes == CF_MAX_NOTES);                     // rate-limited: the note callback runs for the first CF_MAX_NOTES only
    CHECK(g_reports == 0);
    CHECK(!file_exists_pid(GetCurrentProcessId()));     // the one-shot evidence file was NOT consumed
    CHECK(g_cb_done == 0);

    // ---- fatal exceptions in child processes
    for (int sc = 1; sc <= 3; sc++) {
        char exe[MAX_PATH], cmd[2 * MAX_PATH + 40];
        GetModuleFileNameA(NULL, exe, MAX_PATH);
        snprintf(cmd, sizeof cmd, "\"%s\" \"%s\" child %d", exe, g_dirA, sc);
        STARTUPINFOA si = {sizeof si}; PROCESS_INFORMATION pi;
        BOOL ok = CreateProcessA(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
        CHECK(ok);
        if (!ok) continue;
        WaitForSingleObject(pi.hProcess, 30000);
        DWORD ec = 0; GetExitCodeProcess(pi.hProcess, &ec);
        CHECK(ec == 0xC0000005);                        // the game's filter said EXECUTE_HANDLER: the process died of the AV
        CHECK(file_exists_pid(pi.dwProcessId));          // evidence for the fatal one
        if (sc == 3) { CloseHandle(pi.hProcess); CloseHandle(pi.hThread); continue; }   // evidence written (checked above), stale prev skipped, died of the AV
        char p[MAX_PATH + 64]; const char *mk = sc == 1 ? "prev-A.txt" : "prev-B.txt";
        snprintf(p, sizeof p, "%s\\%s", g_dirA, mk);
        FILE *f = fopen(p, "rb"); char b[64] = {0}; if (f) { fread(b, 1, 63, f); fclose(f); }
        CHECK(f != NULL);                                // chained: the previous (game) filter ran
        CHECK(!strcmp(b, "reports=1"));                  // after exactly one report (the handled noise did not count)
        printf("child %d: exit %08lx evidence %d marker '%s'\n", sc, (unsigned long)ec, file_exists_pid(pi.dwProcessId), b);
        CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
    }
    printf("HARNESS %s\n", g_fails ? "FAILED" : "OK");
    return g_fails ? 1 : 0;
}
