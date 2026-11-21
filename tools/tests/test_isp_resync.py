"""Offline test of the item spots roll-table resync (tools/ext/itemspots.c isp_resync -> isp_apply_snapshot).
The two functions (and their helpers) are cut out of itemspots.c as they are, compiled into a small harness with stubs for the
engine / network side, and run: a host table of up to ISP_MAX spots (a mix of shared / unique, held / cooling / waiting spots) is sent
as op 4 + op 8 chunks, every message must stay under 256 bytes (send_gate holds messages with a uint8 length), and a newcomer that
applies the messages in order (and in reverse order) must end with the host's roll numbers / states on every unique spot, untouched
shared spots, and nothing written past the table. Also: an old-style single op 4 (<= ISP_TAB_CHUNK spots) and truncated messages.
Run: python tools/tests/test_isp_resync.py   (needs gcc: PATH or tools/win/ext/msys64/ucrt64/bin; skips without one)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
EXT = os.path.join(TOOLS, "ext")


def find_gcc():
    g = shutil.which("gcc")
    if g:
        return g
    root = os.path.dirname(TOOLS)
    for _ in range(5):
        p = os.path.join(root, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if os.path.exists(p):
            return p
        root = os.path.dirname(root)
    for root in (os.environ.get("T2R_MAIN_ROOT"), "."):     # a checkout elsewhere (build_dll.py does the same)
        p = os.path.join(root or "", "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if root and os.path.exists(p):
            return p
    return None


def cut_function(src, name):
    """the full text of `static ... name(...) { ... }` (brace matched)"""
    m = re.search(r"^static [^\n;{]*\b" + re.escape(name) + r"\([^)]*\)\s*\{", src, re.M)
    assert m, name
    i, depth = m.end() - 1, 0
    while True:
        c = src[i]
        depth += c == "{"
        depth -= c == "}"
        i += 1
        if depth == 0:
            return src[m.start():i]


def cut_line(src, pat):
    m = re.search(pat, src, re.M)
    assert m, pat
    return m.group(0)


HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef struct { const char *item; float off[3]; float q[4]; int w; } isp_cand_t;
#define ISP_MAXC 40
typedef struct { float p[3]; float q[4]; int n; isp_cand_t c[ISP_MAXC]; float dy; int sh, fill, resp; } isp_spot_t;
%(defines)s
#define T2R_MAX_PEERS 8
#define MSG_ISPOT 0x68
#define ISP_FILL_PCT 35
#define ISP_RESPAWN_S 60
static uint64_t g_now = 1000000;
static uint64_t GetTickCount64(void) { return g_now; }
static void xlog(const char *f, ...) { (void)f; }
static void sd_resync(uint32_t to) { (void)to; }
static int g_is_host = 1;
static int isp_host(void) { return g_is_host; }
%(enum)s
%(state)s
static uint8_t g_msgs[16][300]; static uint64_t g_lens[16]; static int g_nmsg, g_bad_len;
static void send_cap(int type, const void *m, uint64_t len, uint8_t to) {
    (void)to; if (type != MSG_ISPOT) g_bad_len = 1;
    if (len > 255) g_bad_len = 1;
    if (g_nmsg < 16) { memcpy(g_msgs[g_nmsg], m, len > 300 ? 300 : len); g_lens[g_nmsg++] = len; }
}
static void (*g_send_tramp)(int, const void *, uint64_t, uint8_t) = send_cap;
%(pt_count)s
%(helpers)s
%(resync)s
%(apply)s

static isp_spot_t SP[ISP_MAX];
struct snap { int st, rolls, taken, kill; uint64_t due; };
static int run(int n, int reverse, int trunc) {
    memset(&g_isp, 0, sizeof g_isp); memset(SP, 0, sizeof SP);
    for (int i = 0; i < n; i++) SP[i].sh = (i %% 3) == 1;
    g_isp.sp = SP; g_isp.n = n; g_isp.active = 1; g_isp.seed = 0x1234;
    struct snap host[ISP_MAX];
    for (int i = 0; i < n; i++) {                            // host state
        g_isp.c[i].rolls = 1 + (i * 7) %% 200; g_isp.c[i].taken = (i %% 5) - 1;
        g_isp.c[i].st = i %% 4 == 0 ? 1 /*HOLD*/ : i %% 4 == 1 ? 2 /*COOL*/ : i %% 4 == 2 ? 0 /*WAIT*/ : 2;
        g_isp.c[i].due = g_now + 1000ULL * (uint64_t)(i %% 90);
        host[i].st = g_isp.c[i].st; host[i].rolls = g_isp.c[i].rolls; host[i].taken = g_isp.c[i].taken; host[i].due = g_isp.c[i].due;
    }
    g_nmsg = 0; g_bad_len = 0; g_is_host = 1;
    isp_resync(3);
    int want_msgs = (n + ISP_TAB_CHUNK - 1) / ISP_TAB_CHUNK;
    if (g_nmsg != want_msgs) { printf("FAIL n=%%d: %%d messages, want %%d\n", n, g_nmsg, want_msgs); return 1; }
    if (g_bad_len) { printf("FAIL n=%%d: a message >= 256 bytes or wrong type\n", n); return 1; }
    for (int k = 0; k < g_nmsg; k++) {
        int op = g_msgs[k][0];
        if ((k == 0) != (op == 4)) { printf("FAIL n=%%d: message %%d op %%d\n", n, k, op); return 1; }
    }
    // the newcomer: every spot behind (rolls 0), nothing held
    memset(g_isp.c, 0, sizeof g_isp.c); g_is_host = 0;
    for (int i = 0; i < n; i++) g_isp.c[i].taken = -1;
    for (int kk = 0; kk < g_nmsg; kk++) {
        int k = reverse ? g_nmsg - 1 - kk : kk;
        uint64_t len = g_lens[k];
        if (trunc && k == g_nmsg - 1) len -= 5;                // a short last message: the spots it no longer carries stay as they were
        uint8_t op = g_msgs[k][0];
        if ((op == 4 && len >= 6) || (op == 8 && len >= 7)) isp_apply_snapshot(g_msgs[k], len);
    }
    int last_chunk_start = (g_nmsg - 1) * ISP_TAB_CHUNK, cut_from = trunc ? n - 2 : n;   // -5 bytes = the last entry gone + 1 byte of the one before
    for (int i = 0; i < n; i++) {
        struct snap *h = &host[i]; typeof(g_isp.c[0]) *c = &g_isp.c[i];
        if (SP[i].sh || (trunc && i >= cut_from && i >= last_chunk_start)) {
            if (c->rolls != 0 || c->st != 0) { printf("FAIL n=%%d spot %%d: shared / not carried, but rolls %%d st %%d\n", n, i, c->rolls, c->st); return 1; }
            continue;
        }
        int want_rolls = h->st == 1 ? h->rolls - 1 : h->rolls, want_st = h->st == 1 ? 0 : 2;
        if (c->rolls != want_rolls || c->st != want_st || c->taken != (h->taken > -1 ? h->taken : -1)) {
            printf("FAIL n=%%d spot %%d: rolls %%d st %%d taken %%d, want %%d %%d %%d\n", n, i, c->rolls, c->st, c->taken, want_rolls, want_st, h->taken);
            return 1;
        }
        uint64_t left = h->st == 1 ? 0 : (h->due > g_now ? (h->due - g_now) / 1000 : 0);
        if (want_st == 2 && c->due != g_now + 1000ULL * left) { printf("FAIL n=%%d spot %%d: due off\n", n, i); return 1; }
    }
    printf("ok   n=%%d%%s%%s: %%d message(s), lengths", n, reverse ? " reversed" : "", trunc ? " truncated" : "", g_nmsg);
    for (int k = 0; k < g_nmsg; k++) printf(" %%llu", (unsigned long long)g_lens[k]);
    printf("\n");
    return 0;
}
int main(void) {
    int bad = 0, ns[] = {1, 9, ISP_TAB_CHUNK - 1, ISP_TAB_CHUNK, ISP_TAB_CHUNK + 1, 77, 2 * ISP_TAB_CHUNK, ISP_MAX};
    for (size_t k = 0; k < sizeof ns / sizeof *ns; k++)
        for (int rev = 0; rev < 2; rev++) bad |= run(ns[k], rev, 0);
    bad |= run(77, 0, 1); bad |= run(ISP_MAX, 0, 1);
    // a hostile op 8 whose start is past the table must not write anything
    memset(&g_isp, 0, sizeof g_isp); g_isp.sp = SP; g_isp.n = 10; g_isp.active = 1;
    uint8_t evil[3 + 4 * 60] = {8, 200, 60}; memset(evil + 3, 9, sizeof evil - 3);
    isp_apply_snapshot(evil, sizeof evil);
    uint8_t evil2[3 + 4 * 60] = {8, 5, 60}; memset(evil2 + 3, 9, sizeof evil2 - 3);
    isp_apply_snapshot(evil2, sizeof evil2);          // claims 60 spots from 5: only 5..9 exist
    for (int i = 0; i < ISP_MAX; i++) if (i >= 10 && (g_isp.c[i].rolls || g_isp.c[i].st)) { printf("FAIL hostile op 8 wrote spot %%d\n", i); bad = 1; }
    if (!bad) printf("ok   hostile op 8 (start past the table, count past the table)\n");
    return bad;
}
"""


def main():
    gcc = find_gcc()
    if not gcc:
        print("skip: no gcc")
        return 0
    src = open(os.path.join(EXT, "itemspots.c"), encoding="utf-8").read()
    pt = open(os.path.join(EXT, "peertrust.h"), encoding="utf-8").read()
    defines = "\n".join(cut_line(src, r"^#define %s\b.*$" % d) for d in ("ISP_MAX", "ISP_TAB_CHUNK"))
    state = cut_line(src, r"^static struct \{\n    uint32_t seed;[\s\S]*?\n\} g_isp;")
    helpers = "\n".join(cut_line(src, r"^static %s.*$" % re.escape(h)) for h in ("int isp_shared(int si) {", "int isp_fill(int si) {", "uint64_t isp_resp_ms(int si) {"))
    code = HARNESS % {
        "defines": defines,
        "enum": cut_line(src, r"^enum \{ ISP_WAIT.*$"),
        "state": state,
        "pt_count": cut_function(pt, "pt_count").replace("static inline", "static"),
        "helpers": helpers,
        "resync": cut_function(src, "isp_resync"),
        "apply": cut_function(src, "isp_apply_snapshot"),
    }
    d = tempfile.mkdtemp(prefix="isp_resync_")
    c, exe = os.path.join(d, "h.c"), os.path.join(d, "h.exe")
    open(c, "w").write(code)
    env = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([gcc, "-std=gnu2x", "-O1", "-Wall", "-Wno-unused-function", "-fsanitize=undefined", "-fsanitize-undefined-trap-on-error", "-o", exe, c],
                       capture_output=True, text=True, env=env)
    if r.returncode:
        print(r.stdout + r.stderr)
        print("FAIL compile")
        return 1
    r = subprocess.run([exe], capture_output=True, text=True, env=env)
    print(r.stdout + r.stderr, end="")
    print("PASS" if r.returncode == 0 else "FAIL")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
