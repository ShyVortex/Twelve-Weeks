"""Offline outage harness for the ext's daemon requests (re/ext-daemon-outage-1019.md).  Run: python outage_test.py [path to gcc dir]
 1. outage_probe.c (compiles tools/ext/outage.h = the ext's own t2r_rpc / backoff / frame check) against outage_fake_daemon.py in every
    misbehaving mode (hang, drop, trickle, garbled / truncated / zero / oversized frames, RST, slow, refused, never-accepting) with the clan worker's
    budgets (connect 3 s, whole reply 4 s) - asserts the call returns inside its budget and classifies the bytes right.
 2. parse_fuzz: the ext's reply parsers (clan_parse, mf_parse, nm_parse, meta_parse, pm_parse, feed_parse) are cut out of t2r-ext.c, compiled with
    stubs and fed thousands of random / mutated / garbled strings, each placed right before a PAGE_NOACCESS guard page (an over-read faults).
"""
import os, re, subprocess, sys, tempfile, time, socket, random

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import outage_fake_daemon as fd

GCC = "gcc"
if len(sys.argv) > 1:
    os.environ["PATH"] = sys.argv[1] + os.pathsep + os.environ["PATH"]
OUT = tempfile.mkdtemp(prefix="outage_")
fails = []


def check(c, msg):
    print(("ok   " if c else "FAIL ") + msg)
    if not c:
        fails.append(msg)


def build(src, exe, extra=()):
    r = subprocess.run([GCC, "-std=gnu2x", "-O2", "-o", exe, src, *extra], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        sys.exit("build failed: " + src)


def probe(port, *args):
    r = subprocess.run([PROBE, "rpc", "127.0.0.1", str(port), *map(str, args)], capture_output=True, text=True, timeout=60)
    m = dict(kv.split("=") for kv in r.stdout.split())
    return {k: int(v) for k, v in m.items()}


PROBE = os.path.join(OUT, "outage_probe.exe")
build(os.path.join(HERE, "outage_probe.c"), PROBE)
r = subprocess.run([PROBE, "backoff"], capture_output=True, text=True)
check("backoff ok" in r.stdout, "backoff: exponential 1.5 s -> 10 s cap, +-25%% jitter, 0 for no failure (%s)" % r.stdout.strip())

# (mode, expect_max_ms, expect_state, note)   state: 1 complete frame, 0 incomplete, -1 cannot fit
CASES = [
    ("ok", 800, 1, "valid frame"),
    ("noread", 800, 1, "reply before the request is read"),
    ("slow:1500", 2500, 1, "slow daemon (1.5 s)"),
    ("slow:6000", 4600, 0, "daemon slower than the 4 s reply budget: worker returns at 4 s"),
    ("hang", 4600, 0, "accepts and never answers (dead tunnel behind a live edge)"),
    ("close", 800, 0, "accepts, closes without a reply"),
    ("rst", 800, 0, "connection reset"),
    ("trickle", 4600, 1, "valid frame at 1 byte / 300 ms (needs ~16 s of the 4 s budget?)"),
    ("trickle_forever", 4600, 0, "header says 900 bytes, 1 byte / 300 ms for 60 s: bounded by the reply budget"),
    ("garble_len", 800, -1, "length 60000: cut at once, never waits for it"),
    ("zerolen", 4600, 0, "frame length 0: never completes, budget ends it"),
    ("short", 800, 0, "header says 50, 10 bytes then close"),
    ("two", 800, 1, "frame + trailing junk"),
    ("halfhdr", 800, 0, "1 byte then close"),
]
for mode, mx, want, note in CASES:
    port, stop = fd.start(mode)
    t0 = time.time()
    res = probe(port, 3000, 4000, 4000, 1023)
    el = (time.time() - t0) * 1000
    stop()
    if mode == "trickle":
        # the valid 55-byte frame needs ~17 s at this rate: the budget (4 s) must cut it, state 0 - the point is the bound
        check(el < mx and res["state"] == 0, "%-16s %-60s %5.0f ms state %d" % (mode, note, el, res["state"]))
    else:
        check(el < mx and res["state"] == want, "%-16s %-60s %5.0f ms state %d sent %d" % (mode, note, el, res["state"], res["sent"]))

# refused: a port nothing listens on
s = socket.socket(); s.bind(("127.0.0.1", 0)); closed = s.getsockname()[1]; s.close()
t0 = time.time(); res = probe(closed, 3000, 4000, 4000, 1023); el = (time.time() - t0) * 1000
check(res["got"] == 0 and res["sent"] == 0 and el < 3300, "refused port: no bytes, not sent, %.0f ms (connect budget 3 s)" % el)
# never accepted: a listener with no accept and a full backlog still lets connect() finish (kernel), so only the reply budget matters: hang case above
# unroutable address: connect() would block ~21 s with the old plain call
r = subprocess.run([PROBE, "rpc", "10.255.255.1", "9", "800", "800", "800", "1023"], capture_output=True, text=True, timeout=60)
m = {k: int(v) for k, v in (kv.split("=") for kv in r.stdout.split())}
check(m["sent"] == 0 and m["ms"] < 1500, "unroutable address: gives up in %d ms (connect budget 0.8 s; the old blocking connect took ~21 s)" % m["ms"])

# ---------------------------------------------------------------- parser fuzz
src = open(os.path.join(EXT, "t2r-ext.c"), "rb").read().decode("utf-8").replace("\r\n", "\n")


def fn(name):
    m = re.search(r"static void %s\(.*?\n}\n" % name, src, re.S)
    assert m, name
    return m.group(0)


def td(name):
    m = re.search(r"typedef struct \{[^}]*\} %s;" % name, src)
    assert m, name
    return m.group(0)


defs = "\n".join(re.search(r"#define %s [^\n/]*" % d, src).group(0) for d in
                 ("FEED_MAX", "FEED_LEN", "PACK_MAPS_MAX", "PACK_BASE_IDX", "PACK_LVL_MAX"))
gen = r'''#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
%s
%s
static CRITICAL_SECTION g_clan_cs;
static clan_t g_clan; static mf_t g_mf; static nm_t g_nm; static meta_t g_meta; static feed_t g_feed;
static char g_pm_level[PACK_MAPS_MAX][PACK_LVL_MAX]; static char g_pack_acc[256];
static volatile LONG g_clan_ver, g_mf_ver, g_nm_ver, g_meta_ver, g_feed_ver, g_pack_ver;
%s
int main(void) {
    InitializeCriticalSection(&g_clan_cs);
    SYSTEM_INFO si; GetSystemInfo(&si);
    size_t pg = si.dwPageSize;
    char *base = VirtualAlloc(NULL, pg * 2, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    DWORD old; VirtualProtect(base + pg, pg, PAGE_NOACCESS, &old);
    const char *seeds[] = {
        "fac=1 st=1 day=3 h=4 hu=0 s=0 need=2 wk=1 lday=2 lparts=40 ag1=2 ag2=3 ag3=4 mx=9 rw=1 rl=2",
        "st=1 n=3 m0=2 v0=1 m1=3 v1=0 m2=4 v2=2 my=-1 w=-1 pc=2 p0=ALICE_B pv0=1 p1=BOB pv1=0",
        "ok=1 name=Joe_Q tag=ABC err=-", "bc1=2 bc7=1 bp=3 ba=1 bn=2 mi=2 mp=4 ml=9 mr15=3 mr99=1 mg1=3 mg3=5 lmd=-1 mf=7",
        "n=2\nrec1|first line of the feed\nrec2|second\n\n|\nnobar\n", "on=1 acc=a,b,c pm22=lvl_a pm53=lvl_b pm9999=zzz",
    };
    unsigned seed = 12345; srand(seed);
    long runs = 0;
    for (int it = 0; it < 60000; it++) {
        char tmp[600]; int n;
        const char *sd = seeds[it %% 6];
        n = (int)strlen(sd);
        memcpy(tmp, sd, n + 1);
        int mode = it %% 5;
        if (mode == 1) for (int k = 0; k < 4; k++) tmp[rand() %% n] = (char)(rand() & 0x7f ? rand() & 0x7f : '=');   // byte flips
        if (mode == 2) { n = rand() %% (n + 1); tmp[n] = 0; }                                                        // truncation
        if (mode == 3) { n = 1 + rand() %% 500; for (int k = 0; k < n; k++) tmp[k] = "=_ \n|abcpmvn0123456789-"[rand() %% 24]; tmp[n] = 0; }   // soup
        if (mode == 4) { n = 400; memset(tmp, 'A' + (it %% 7), n); tmp[n] = 0; if (it %% 2) { tmp[3] = '='; tmp[200] = ' '; tmp[201] = 'm'; tmp[202] = '0'; tmp[203] = '='; } }   // long tokens
        n = (int)strlen(tmp);
        char *p = base + pg - (n + 1);           // NUL right before the guard page
        memcpy(p, tmp, n + 1);
        clan_parse(p); mf_parse(p); nm_parse(p, 0xD0); meta_parse(p); pm_parse(p); feed_parse(p);
        runs++;
    }
    printf("fuzz ok %%ld inputs x 6 parsers\n", runs);
    return 0;
}
''' % (defs, "\n".join(td(t) for t in ("clan_t", "mf_t", "nm_t", "meta_t", "feed_t")),
       "\n".join(fn(f) for f in ("clan_parse", "mf_parse", "nm_parse", "meta_parse", "pm_parse", "feed_parse")))
gsrc = os.path.join(OUT, "parse_fuzz.c")
open(gsrc, "w").write(gen)
FUZZ = os.path.join(OUT, "parse_fuzz.exe")
build(gsrc, FUZZ)
r = subprocess.run([FUZZ], capture_output=True, text=True, timeout=120)
check(r.returncode == 0 and "fuzz ok" in r.stdout, "parse fuzz: %s (rc %d)" % (r.stdout.strip() or r.stderr.strip(), r.returncode))

print("\n%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
