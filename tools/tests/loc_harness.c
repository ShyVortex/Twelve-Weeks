// test harness of tools/ext/loc.c (the localisation layer): reads lines from stdin, prints the translation of each (language 0 = pl)
// or, with the argument "draw", the diacritics-folded draw variant. Built and run by tools/tests/test_loc.py.
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
static uint64_t g_frame = 1000;
static char *g_winmm;
#define VMA(x) 0
static void xlog(const char *f, ...) { (void)f; }
static FILE *exe_side_open(const char *n, const char *m) { (void)n; (void)m; return NULL; }
static uint64_t dc_call(uint64_t sid, int argc, uint64_t *argv) { (void)sid; (void)argc; (void)argv; return 0; }
#include "../ext/loc.c"
int main(int argc, char **argv) {
    int draw = argc > 1 && !strcmp(argv[1], "draw");
    g_loc_cur = argc > 1 && !strcmp(argv[1], "en") ? -1 : 0;
    if (g_loc_cur >= 0) loc_build(g_loc_cur);
    char line[2048];
    while (fgets(line, sizeof line, stdin)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        // "\\n" in the input = a newline
        char buf[2048]; size_t o = 0;
        for (size_t i = 0; line[i] && o < sizeof buf - 1; i++) {
            if (line[i] == '\\' && line[i + 1] == 'n') { buf[o++] = '\n'; i++; } else buf[o++] = line[i];
        }
        buf[o] = 0;
        const char *t = draw ? loc_tr_draw(buf) : loc_tr(buf);
        for (const char *p = t; *p; p++) { if (*p == '\n') fputs("\\n", stdout); else fputc(*p, stdout); }
        fputc('\n', stdout);
    }
    return 0;
}
