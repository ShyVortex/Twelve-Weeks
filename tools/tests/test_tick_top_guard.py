"""Tick-top guard (re/boot-exit-1019.md): nothing t2r_tick runs BEFORE its `if (!g_winmm) { ...init... }` block may touch winmm memory.

Why: g_winmm is NULL until that block resolves it, and the crash handler + t2r-ext.log are installed inside it. A pre-init callee that does VMA(x)
(= g_winmm + x - 0x180000000, i.e. a read near address 0x138090) faults on the first frame: the game exits silently at launch, no log, no dump.
This happened twice (perf_note_gap via match_substate(); sq_tick) and no offline test can see it, so this one reads the source.

What it does:
  1. Builds one text from tools/ext/t2r-ext.c with every `#include "x.c|x.h"` that lives in tools/ext expanded in place (unity build), comments and
     string literals blanked, with file:line kept per line.
  2. Collects function definitions (brace depth 0) and function-like #define macros.
  3. Takes the part of t2r_tick before the first `if (!g_winmm) {` and checks it like a function body: every call to a function defined in the unity
     build is followed (bounded depth, MAX_DEPTH) and a HAZARD is reported when one is reachable UNGUARDED:
        - VMA(...)                       (always a g_winmm-relative read)
        - a bare use of g_winmm that is not part of an if / while condition (pointer arithmetic, a cast, a deref)
        - a call to a callee that itself has such a hazard (reported with the chain)
     A position counts as GUARDED when it is after a statement-level `if (!g_winmm ...) return`, or after `if (!FLAG ...) return` for a FLAG in
     INIT_FLAGS (set only by code that runs after the init block), or inside the block / statement of an `if (... g_winmm ...)` with a positive g_winmm term.
  4. Functions in ALLOW are skipped (each with the reason it is safe).
Limits (regex + brace matching, not a C parser): calls through function pointers / macros defined outside tools/ext are not followed; `#if` branches are
all analysed (both T2R_RELEASE variants); a guard must be written in one of the forms above (an equivalent but unusual form is a false alarm: rewrite it
in the standard form or add it to ALLOW with a comment); a hazard hidden in a callee through a global function pointer is invisible. The runtime net for what
this misses is boot_veh in t2r-ext.c ('crash: EARLY FAULT' in t2r-ext-boot.txt).
Run: python tools/tests/test_tick_top_guard.py"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
EXT = os.path.join(TOOLS, "ext")
MAX_DEPTH = 8

# flags that are only ever set by code running AFTER the init block (hooks installed there), so `if (!flag) return` is a valid early-out
INIT_FLAGS = {
    "g_htr_on": "holster_trace.c: set by htr_install, called from the init block",
    "g_gl_on": "glass.c: set by install_glass_sync, called from the init block",
    "g_ragctl_cnt": "pointer to the guard hook's counter, set by install_ragctl_guard (init block)",
    "g_ownh_cnt": "pointer to the guard hook's counter, set by install_ownh_guard (init block)",
}
# function -> why it is safe although the analysis cannot prove it
ALLOW = {}   # function -> why it is safe although the analysis cannot prove it (none needed today)
KEYWORDS = {"if", "while", "for", "switch", "return", "sizeof", "defined", "else", "do", "case", "typeof", "alignof", "__builtin_return_address",
            "__attribute__", "_Static_assert", "static_assert", "offsetof"}


def blank(src):
    """Blank comments and string / char literals, keep every newline and the length."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", src[i:j])); i = j
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(c + " " * (j - i - 2) + c if j - i >= 2 else c); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def load(main_text=None):
    """-> (list of (file, lineno, text) physical lines, expanded)."""
    lines, seen = [], set()

    def add(name, text):
        for k, ln in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
            m = re.match(r'\s*#\s*include\s+"([^"]+\.(?:c|h))"', ln)
            if m and os.path.exists(os.path.join(EXT, m.group(1))) and m.group(1) not in seen and m.group(1) != "t2r-ext.c":
                seen.add(m.group(1))
                add(m.group(1), open(os.path.join(EXT, m.group(1)), encoding="utf-8", errors="replace").read())
            else:
                lines.append((name, k, ln))
    if main_text is None:
        main_text = open(os.path.join(EXT, "t2r-ext.c"), encoding="utf-8", errors="replace").read()
    add("t2r-ext.c", main_text)
    return lines


class Unity:
    def __init__(self, lines):
        self.lines = lines
        text = blank("\n".join(l[2] for l in lines))
        # preprocessor lines: collect function-like macros (with continuations), blank them for the function scan
        tl = text.split("\n")
        self.macros = {}
        i = 0
        while i < len(tl):
            if tl[i].lstrip().startswith("#"):
                j = i
                body = tl[i]
                while body.rstrip().endswith("\\") and j + 1 < len(tl):
                    j += 1; body += "\n" + tl[j]
                m = re.match(r"\s*#\s*define\s+([A-Za-z_]\w*)\(", body)
                if m:
                    self.macros[m.group(1)] = (i, body)
                for k in range(i, j + 1):
                    tl[k] = " " * len(tl[k])
                i = j + 1
            else:
                i += 1
        self.text = "\n".join(tl)
        self.starts = [0]
        for ln in self.text.split("\n"):
            self.starts.append(self.starts[-1] + len(ln) + 1)
        self.funcs = {}   # name -> list of (body_start, body_end)  (indexes into self.text, braces excluded)
        self._scan()

    def where(self, pos):
        import bisect
        k = bisect.bisect_right(self.starts, pos) - 1
        f, ln, _ = self.lines[min(k, len(self.lines) - 1)]
        return "%s:%d" % (f, ln)

    def _scan(self):
        t = self.text
        depth, hdr_start, i, n = 0, 0, 0, len(t)
        while i < n:
            c = t[i]
            if c == "{":
                if depth == 0:
                    hdr = t[hdr_start:i]
                    m = re.search(r"([A-Za-z_]\w*)\s*\((?:[^()]|\([^()]*\))*\)\s*(?:__attribute__\(\([^)]*\)\))?\s*$", hdr)
                    if m and not re.search(r"(^|\W)(typedef|struct|enum|union)\b[^()]*$", hdr[:m.start()]) and "=" not in hdr[m.start():m.start() + 1]:
                        end = self._match(i)
                        self.funcs.setdefault(m.group(1), []).append((i + 1, end))
                        i = end + 1; hdr_start = i
                        continue
                    # initializer / struct body: skip it whole
                    end = self._match(i)
                    i = end + 1
                    continue
                depth += 1
            elif c == ";" and depth == 0:
                hdr_start = i + 1
            elif c == "}":
                hdr_start = i + 1
            i += 1

    def _match(self, i):
        t, d = self.text, 0
        while i < len(t):
            if t[i] == "{": d += 1
            elif t[i] == "}":
                d -= 1
                if d == 0: return i
            i += 1
        return len(t) - 1


def paren_end(t, i):
    """index of the ')' matching the '(' at i."""
    d = 0
    while i < len(t):
        if t[i] == "(": d += 1
        elif t[i] == ")":
            d -= 1
            if d == 0: return i
        i += 1
    return len(t) - 1


def stmt_end(t, i):
    """end index of the statement / block starting at the first non-space char at or after i."""
    while i < len(t) and t[i].isspace(): i += 1
    if i < len(t) and t[i] == "{":
        d = 0
        while i < len(t):
            if t[i] == "{": d += 1
            elif t[i] == "}":
                d -= 1
                if d == 0: return i
            i += 1
        return len(t) - 1
    if t.startswith("if", i) and re.match(r"if\b", t[i:]):   # else-less nested if: take its own statement
        j = t.index("(", i); j = paren_end(t, j) + 1
        e = stmt_end(t, j)
        m = re.match(r"\s*else\b", t[e + 1:])
        return stmt_end(t, e + 1 + m.end()) if m else e
    d = 0
    while i < len(t):
        if t[i] in "({[": d += 1
        elif t[i] in ")}]": d -= 1
        elif t[i] == ";" and d <= 0: return i
        i += 1
    return len(t) - 1


def analyse_region(u, a, b, depth, chain, memo, stack, allow_extra=()):
    """Hazards in text[a:b] (a function body or the tick-top prefix): list of (pos, description)."""
    t = u.text
    seg = t[a:b]
    # --- guarded ranges -------------------------------------------------------------------------------------------------
    guard_from = b   # everything from here to b is guarded by an early return
    d = 0
    # statement-level early-out guards: depth tracking over the segment
    depth_at = []
    dd = 0
    for ch in seg:
        depth_at.append(dd)
        if ch == "{": dd += 1
        elif ch == "}": dd -= 1
    flags = "|".join(["g_winmm"] + list(INIT_FLAGS))
    for m in re.finditer(r"\bif\s*\(\s*!\s*(?:%s)\b" % flags, seg):
        if depth_at[m.start()] != 0:
            continue
        pe = paren_end(seg, seg.index("(", m.start()))
        after = seg[pe + 1:]
        if re.match(r"\s*return\b", after) or re.match(r"\s*\{\s*return\b", after):
            guard_from = min(guard_from, a + pe + 1)
    ranges = []   # (start, end) absolute guarded by a positive g_winmm condition
    for m in re.finditer(r"\b(?:if|while)\s*\(", seg):
        p0 = seg.index("(", m.start())
        pe = paren_end(seg, p0)
        cond = seg[p0:pe + 1]
        if re.search(r"(?<![!\w])g_winmm\b", cond) and "||" not in cond:
            ranges.append((a + p0, a + stmt_end(seg, pe + 1)))
    cond_ranges = []   # absolute if/while condition ranges: a g_winmm in there is a check, not a deref
    for m in re.finditer(r"\b(?:if|while)\s*\(", seg):
        p0 = seg.index("(", m.start())
        cond_ranges.append((a + p0, a + paren_end(seg, p0)))

    def guarded(p):
        return p >= guard_from or any(s <= p <= e for s, e in ranges)

    def in_cond(p):
        return any(s <= p <= e for s, e in cond_ranges)

    out = []
    # --- direct hazards -------------------------------------------------------------------------------------------------
    for m in re.finditer(r"\bVMA\s*\(", seg):
        p = a + m.start()
        if not guarded(p):
            out.append((p, "VMA(...) read before g_winmm is known"))
    for m in re.finditer(r"\bg_winmm\b", seg):
        p = a + m.start()
        if guarded(p) or in_cond(p):
            continue
        out.append((p, "bare use of g_winmm (NULL until the init block)"))
    # --- calls ------------------------------------------------------------------------------------------------------------
    for m in re.finditer(r"(?<![\w.>])([A-Za-z_]\w*)\s*\(", seg):
        name = m.group(1)
        if name in KEYWORDS or name == "VMA" or name in ALLOW or name in allow_extra:
            continue
        p = a + m.start()
        if guarded(p) or depth >= MAX_DEPTH:
            continue
        callee = None
        if name in u.funcs:
            callee = [(s, e) for s, e in u.funcs[name]]
        elif name in u.macros:
            i0, body = u.macros[name]
            callee = None
            if re.search(r"\bVMA\s*\(|\bg_winmm\b", body):
                out.append((p, "macro %s() expands to winmm-relative access (%s)" % (name, u.where(u.starts[i0]))))
            continue
        if not callee or name in stack:
            continue
        key = name
        if key not in memo:
            memo[key] = None
            res = []
            for s, e in callee:
                res += analyse_region(u, s, e, depth + 1, chain + [name], memo, stack | {name})
            memo[key] = res
        if memo[key]:
            first = memo[key][0]
            out.append((p, "calls %s(), which reaches: %s" % (name, first[1])))
    return sorted(out)


def check_tick(u, report):
    tick = u.funcs.get("t2r_tick")
    if not tick:
        report.append("t2r_tick not found"); return
    s, e = tick[0]
    body = u.text[s:e]
    m = re.search(r"\bif\s*\(\s*!\s*g_winmm\s*\)\s*\{", body)
    if not m:
        report.append("t2r_tick: the `if (!g_winmm) {` init block was not found (test needs updating?)"); return
    pre_end = s + m.start()
    pre = u.text[s:pre_end]
    ncalls = len(re.findall(r"(?<![\w.>])[A-Za-z_]\w*\s*\(", pre))
    memo = {}
    res = analyse_region(u, s, pre_end, 0, ["t2r_tick"], memo, {"t2r_tick"})
    for p, d in res:
        report.append("t2r_tick (%s): %s" % (u.where(p), d))
    return ncalls


def check_source(main_text=None):
    u = Unity(load(main_text))
    rep = []
    n = check_tick(u, rep)
    return rep, n


# --- self-test snippets --------------------------------------------------------------------------------------------------
OLD_SQ = """
static HMODULE g_winmm;
#define VMA(x) ((uintptr_t)g_winmm + ((x) - 0x180000000ULL))
static void sq_tick(void) {
    unsigned me = *(unsigned *)VMA(0x180138090);
    (void)me;
}
void t2r_tick(void) {
    sq_tick();
    if (!g_winmm) { g_winmm = 0; }
}
"""
FIXED_SQ = OLD_SQ.replace("    unsigned me", "    if (!g_winmm) return;\n    unsigned me")
VIA_HELPER = """
static HMODULE g_winmm;
#define VMA(x) ((uintptr_t)g_winmm + ((x) - 0x180000000ULL))
static unsigned match_substate(void) { return *(unsigned *)VMA(0x180138090); }
static void note_gap(void) { if (match_substate() != 6) return; }
static void outer(void) { note_gap(); }
void t2r_tick(void) {
    outer();
    if (!g_winmm) { g_winmm = 0; }
}
"""
COND_OK = """
static HMODULE g_winmm; static int g_on;
#define VMA(x) ((uintptr_t)g_winmm + ((x) - 0x180000000ULL))
static void t(void) {
    if (!g_on) return;
    if (g_winmm) { unsigned *p = (unsigned *)VMA(1); (void)p; }
    if (x && g_winmm) { char *w = (char *)g_winmm; (void)w; }
}
void t2r_tick(void) {
    t();
    if (!g_winmm) { g_winmm = 0; }
}
"""
OLD_TICK_COMMIT = "3141a8a6"


def main():
    fails = []

    def check(c, w):
        print(("ok   " if c else "FAIL ") + w)
        if not c: fails.append(w)

    for name, snip, want in (("synthetic pre-fix sq_tick", OLD_SQ, True), ("synthetic fixed sq_tick", FIXED_SQ, False),
                             ("synthetic hazard hidden 3 calls deep (match_substate)", VIA_HELPER, True), ("synthetic guarded-by-condition forms", COND_OK, False)):
        u = Unity([("snip.c", i + 1, l) for i, l in enumerate(snip.split("\n"))])
        r = []
        check_tick(u, r)
        check(bool(r) == want, "%s: %s" % (name, "flagged " + r[0] if r else "clean"))
    # the real pre-fix file (git history): must be flagged naming sq_tick
    try:
        old = subprocess.run(["git", "show", OLD_TICK_COMMIT + ":tools/ext/t2r-ext.c"], cwd=ROOT, capture_output=True, timeout=60)
        old_text = old.stdout.decode("utf-8", "replace") if old.returncode == 0 and old.stdout else None
    except Exception:
        old_text = None
    if old_text:
        rep, _ = check_source(old_text)
        check(any("sq_tick" in r for r in rep), "pre-fix t2r-ext.c (%s) is flagged for sq_tick: %s" % (OLD_TICK_COMMIT, rep[0] if rep else "NOT FLAGGED"))
    else:
        print("skip pre-fix file check (git history for %s not available)" % OLD_TICK_COMMIT)
    # the current tree
    rep, n = check_source()
    check(n is not None and n >= 8, "t2r_tick has pre-init calls to analyse (%s found)" % n)
    for r in rep:
        check(False, "tick-top hazard: " + r)
    if not rep:
        check(True, "no unguarded winmm access reachable from t2r_tick before the g_winmm init block")
    print("%d failure(s)" % len(fails) if fails else "all ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
