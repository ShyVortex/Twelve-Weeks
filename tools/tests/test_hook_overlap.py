"""Static hook / patch overlap check for the ext (generalises test_send_hook_unique.py; re/hook-audit-1019.md).

install_sendevent_hook patched the winmm function install_send_hook also patches; the second prologue check failed and a build shipped with every
ext peer message silently disabled. This test extracts every code / data patch the ext source writes and FAILS when two different installer functions
write overlapping bytes of the same module (or one writes bytes winmm_patches.py already changed), unless the pair is in ALLOW below (documented chain).

How targets are found (no compiler, no game): every function in tools/ext/*.c|*.h is scanned for VirtualProtect(ARG0, LEN, PAGE_*WRITE...) - the one call
every installer makes before it writes (the ext's t2r_vprot wrapper records the same calls at runtime, hookreg.h). ARG0's base variable is resolved
through the function's own assignment (`f = (uint8_t *)VMA(0x...)`, `exe + 0x...`, `GetModuleHandleW(NULL) + 0x...`, `+ k` offsets); LEN is a literal,
`sizeof expect` (the expect[N] declaration) or the memcmp length. Patches whose target is computed at run time (tables, loops, vtables of heap objects)
are listed as DYNAMIC: they cannot be checked statically (the runtime registry covers them: 'HOOK CONFLICT' in t2r-ext.log).

  python tools/tests/test_hook_overlap.py            # the test (exit 1 on overlap / unregistered raw VirtualProtect / un-prefixed failure lines)
  python tools/tests/test_hook_overlap.py --table    # markdown inventory (static + dynamic) for re/hook-audit-1019.md
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
EXT = os.path.join(TOOLS, "ext")
sys.path.insert(0, os.path.join(TOOLS, "features"))

# Intentional chains: (installer A, installer B) may patch overlapping bytes of the same module. Keep in step with HR_ALLOW in tools/ext/hookreg.h.
# (empty: the audit found none that is intentional; the pairs the audit found are listed in KNOWN below until they are fixed)
ALLOW = set()
# Known overlaps / known never-installed hooks found by the audit (re/hook-audit-1019.md), documented instead of silently accepted.
# key = frozenset({installer A, installer B}); value = why. A NEW pair that is not here fails the test.
KNOWN = {
    frozenset({"install_msg_hook", "install_notify_filter"}): "install_notify_filter is DEAD CODE (never called; install_msg_hook owns winmm 0x18000BC00 and drops the connection texts itself). Checked below: it must stay uncalled.",
}
# static VirtualProtect-less failure lines that are deliberately plain xlog (opt-outs, data differences): (file, substring of the line)
PLAIN_OK = ("opt-out", "t2r-no-", "ignored", "left on", "no-hooks.txt", "pair-framing camera", "menu camera stays")

FN_RE = re.compile(r"^(?:static\s+|__declspec\(dllexport\)\s+)?(?:inline\s+)?[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?://.*)?\{\s*$")
VP_RE = re.compile(r"\bVirtualProtect\(")
PAGE_W = re.compile(r"PAGE_(?:EXECUTE_)?(?:READWRITE|WRITECOPY)")
ADDR_RE = re.compile(r"(VMA\(0x([0-9A-Fa-f]+)(?:ULL)?\)|(?:\(uint8_t \*\))?(?:exe|base|GetModuleHandleW\(NULL\)|\(uint8_t \*\)GetModuleHandleW\(NULL\))\s*\)?\s*\+\s*0x([0-9A-Fa-f]+))")


def split_args(s, i):
    depth, cur, args, j = 0, i, [], i
    while j < len(s):
        c = s[j]
        if c in "([":
            depth += 1
        elif c in ")]":
            if depth == 0:
                args.append(s[cur:j].strip())
                return args, j
            depth -= 1
        elif c == "," and depth == 0:
            args.append(s[cur:j].strip())
            cur = j + 1
        elif c == '"':
            j += 1
            while s[j] != '"':
                if s[j] == "\\":
                    j += 1
                j += 1
        j += 1
    return None, None


def src_files():
    out = []
    for f in sorted(glob.glob(os.path.join(EXT, "*.c")) + glob.glob(os.path.join(EXT, "*.h"))):
        if os.path.basename(f) == "t2r-ext.c" or os.path.getsize(f) < 600000:     # (skips the generated data headers)
            out.append(f)
    return out


def functions(text):
    """-> [(name, start_line, [lines])] for column-0 function definitions (the ext's style)."""
    lines = text.split("\n")
    res, i = [], 0
    while i < len(lines):
        m = FN_RE.match(lines[i].rstrip("\r"))
        if m and not lines[i].startswith(("}", " ", "\t", "#", "//")):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("}"):
                j += 1
            res.append((m.group(1), i + 1, lines[i:j + 1]))
            i = j
        i += 1
    return res


def resolve(var, body):
    """base address expression of `var` in the function body: ('winmm'|'exe', rva) or None"""
    base = re.match(r"\(?\s*(?:\(\w[\w\s\*]*\)\s*)?([A-Za-z_]\w*)\s*\)?\s*(?:\+\s*(0x[0-9A-Fa-f]+|\d+))?\s*$", var)
    if not base:
        return None
    name, add = base.group(1), int(base.group(2), 0) if base.group(2) else 0
    for ln in body:
        m = re.search(r"(?<![\w.>])" + re.escape(name) + r"\s*=\s*([^;]*);", ln)
        if not m:
            continue
        rhs = m.group(1)
        if re.search(r"VMA\(0x[0-9A-Fa-f]+(?:ULL)?\)\s*\)\s*\(", rhs):    # `((fn_lookup)VMA(0x...))(sid)`: a CALL of a winmm function, not a patch target
            continue
        a = ADDR_RE.search(rhs)
        if not a:
            continue
        if a.group(2):
            rva = int(a.group(2), 16) - 0x180000000
            mod = "winmm"
        else:
            rva = int(a.group(3), 16)
            mod = "exe"
        tail = rhs[a.end():]
        t = re.match(r"\s*\)?\s*\+\s*(0x[0-9A-Fa-f]+|\d+)\b", tail)
        if t:
            rva += int(t.group(1), 0)
        return mod, rva + add
    return None


def length(expr, body):
    expr = expr.strip()
    try:
        return int(expr, 0)
    except ValueError:
        pass
    m = re.match(r"sizeof\s+(\w+)$", expr)
    if m:
        for ln in body:
            d = re.search(r"\b" + m.group(1) + r"\s*\[\s*(\d+|0x[0-9A-Fa-f]+)\s*\]", ln)
            if d:
                return int(d.group(1), 0)
    return None


# patch helpers that take the target as an argument: name -> (kind of the address argument, index of the length argument or a literal length)
#   kind: winmm_va (0x18....), winmm_rva, exe_va (0x14....), exe_rva, expr (a pointer expression / variable resolved in the caller)
HELPERS = {
    "faction_hook_at": ("winmm_va", 2), "pa_inline_hook": ("winmm_va", 2), "kf_patch": ("winmm_va", 2), "sk_jmp": ("winmm_va", 2),
    "xb_hook_exe": ("exe_rva", 2), "hfix_patch": ("exe_rva", 2), "sd_hook_exe": ("exe_rva", 2), "vdf_inline": ("exe_va", 2),
    "vegq_redirect": ("exe_rva", 5), "pa_redirect_call": ("winmm_rva", 5), "pa_ovr_site": ("winmm_rva", 7),
    "decal_diag_hook": ("expr", 1), "spp_hook5": ("expr", 5), "ns_patch": ("expr", 2),
}


def helper_calls(name, body, where0, static, dynamic):
    for k, ln in enumerate(body):
        for h, (kind, lenspec) in HELPERS.items():
            if h == name:
                continue
            for m in re.finditer(r"(?<![\w.])" + h + r"\(", ln):
                args, _ = split_args(ln, m.end())
                if not args:
                    continue
                where = "%s:%d" % (where0[0], where0[1] + k)
                a0 = args[0]
                n = lenspec if isinstance(lenspec, int) and lenspec > 7 or h in ("vegq_redirect", "pa_redirect_call", "pa_ovr_site", "spp_hook5", "decal_diag_hook") and isinstance(lenspec, int) and lenspec > 1 else None
                if isinstance(lenspec, int) and h in ("vegq_redirect", "pa_redirect_call", "pa_ovr_site", "spp_hook5"):
                    n = lenspec
                elif len(args) > lenspec:
                    n = length(args[lenspec], body)
                if h == "decal_diag_hook":
                    n = length(args[1], body)
                rr = None
                if kind in ("winmm_va", "winmm_rva", "exe_va", "exe_rva"):
                    try:
                        v = int(a0.split("+")[0].strip(), 0)
                        base = {"winmm_va": ("winmm", 0x180000000), "winmm_rva": ("winmm", 0), "exe_va": ("exe", 0x140000000), "exe_rva": ("exe", 0)}[kind]
                        rr = (base[0], v - base[1])
                    except ValueError:
                        rr = None
                else:
                    rr = resolve(a0, body)
                    if not rr:
                        e = ADDR_RE.search(a0)
                        if e:
                            rr = ("winmm", int(e.group(2), 16) - 0x180000000) if e.group(2) else ("exe", int(e.group(3), 16))
                if rr:
                    static.append((rr[0], rr[1], rr[1] + (n or 1), name + ">" + h, where))
                else:
                    dynamic.append((name + ">" + h, where, a0, "?"))


def table_sites(name, body, where0, static):
    """`p = exe + SITES[i];` with `static const uint32_t SITES[] = {0x..., ...}` in the same function (exe RVAs), patched through the function's VirtualProtect"""
    text = "\n".join(body)
    for m in re.finditer(r"([A-Za-z_]\w*)\s*=\s*(?:\(uint8_t \*\))?(?:exe|base)\s*\+\s*([A-Za-z_]\w*)\[\w+\]\s*;", text):
        arr = re.search(r"\b" + m.group(2) + r"\s*\[\s*\]\s*=\s*\{([^}]*)\}", text)
        vp = re.search(r"VirtualProtect\(\s*" + m.group(1) + r"\s*,\s*(\d+)\s*,\s*PAGE_EXECUTE_READWRITE", text)
        if arr and vp:
            for v in re.findall(r"0x[0-9A-Fa-f]+", arr.group(1)):
                static.append(("exe", int(v, 16), int(v, 16) + int(vp.group(1)), name + "[table]", "%s:%d" % where0))


def htr_sites(static):
    """holster_trace.c HTR_SITES: {rva, len, jat, HK_KIND, {bytes}} - each site is patched by htr_patch_site (a jmp over `len` bytes)"""
    f = os.path.join(EXT, "holster_trace.c")
    if not os.path.exists(f):
        return
    for no, ln in enumerate(open(f, "rb").read().decode("utf-8", "replace").split("\n"), 1):
        m = re.match(r"\s*\{0x([0-9a-fA-F]+),\s*(\d+),\s*(?:0x[0-9a-fA-F]+|\d+),\s*(HK_\w+),", ln)
        if m:
            static.append(("exe", int(m.group(1), 16), int(m.group(1), 16) + int(m.group(2)), "htr_patch_site[%s]" % m.group(3), "holster_trace.c:%d" % no))


def extract():
    """-> (static patches [(mod, lo, hi, func, 'file:line')], dynamic [(func, 'file:line', arg0, len)], raw_vp)"""
    static, dynamic = [], []
    for f in src_files():
        text = open(f, "rb").read().decode("utf-8", "replace")
        for name, line0, body in functions(text):
            for k, ln in enumerate(body):
                for m in VP_RE.finditer(ln):
                    args, _ = split_args(ln, m.end())
                    if not args or len(args) < 3 or not PAGE_W.search(args[2]):
                        continue
                    where = "%s:%d" % (os.path.basename(f), line0 + k)
                    r = resolve(args[0], body)
                    n = length(args[1], body)
                    if r and n:
                        static.append((r[0], r[1], r[1] + n, name, where))
                    else:
                        dynamic.append((name, where, args[0], args[1]))
            helper_calls(name, body, (os.path.basename(f), line0), static, dynamic)
            table_sites(name, body, (os.path.basename(f), line0), static)
    htr_sites(static)
    return static, dynamic


def winmm_patch_ranges():
    try:
        import winmm_patches as wp
    except Exception:
        return []
    out = []
    for key, p in wp.PATCHES.items():
        if "vma" in p and "orig" in p:
            rva = p["vma"] - 0x180000000
            out.append(("winmm", rva, rva + len(p["orig"]), "winmm_patches:" + key, "winmm_patches.py"))
    return out


def overlaps(static):
    res = []
    for i in range(len(static)):
        for j in range(i + 1, len(static)):
            a, b = static[i], static[j]
            if a[0] != b[0] or not (a[1] < b[2] and b[1] < a[2]) or a[3] == b[3]:
                continue
            res.append((a, b))
    return res


def table():
    static, dynamic = extract()
    print("| module | target (RVA) | len | installer | site |")
    print("|---|---|---|---|---|")
    for mod, lo, hi, fn, where in sorted(static):
        print("| %s | 0x%X | %d | %s | %s |" % (mod, lo, hi - lo, fn, where))
    print("\nDYNAMIC (target computed at run time): %d" % len(dynamic))
    for fn, where, a0, n in sorted(dynamic):
        print("| dyn | `%s` | `%s` | %s | %s |" % (a0, n, fn, where))


def main():
    if "--table" in sys.argv:
        table()
        return 0
    fails = []
    static, dynamic = extract()
    if len(static) < 40:
        fails.append("extractor found only %d static patch targets (expected 100+): the source style changed, fix the extractor" % len(static))
    # 1. two installers on the same bytes
    for a, b in overlaps(static):
        pair = frozenset((a[3], b[3]))
        if pair in ALLOW or pair in KNOWN:
            continue
        fails.append("OVERLAP %s 0x%X..0x%X (%s %s) vs 0x%X..0x%X (%s %s)" % (a[0], a[1], a[2], a[3], a[4], b[1], b[2], b[3], b[4]))
    # 2. ext patches vs winmm_patches.py (the ext checks its expect bytes against the winmm-patched image: a winmm patch inside an ext target changes them)
    wp = winmm_patch_ranges()
    for a in static:
        for w in wp:
            if a[0] == "winmm" and a[1] < w[2] and w[1] < a[2] and frozenset((a[3], w[3])) not in ALLOW and frozenset((a[3], w[3])) not in KNOWN:
                fails.append("ext patch %s 0x%X..0x%X (%s) overlaps %s 0x%X..0x%X" % (a[3], a[1], a[2], a[4], w[3], w[1], w[2]))
    ext0 = open(os.path.join(EXT, "t2r-ext.c"), "rb").read().decode("utf-8", "replace")
    if re.search(r"^\s*install_notify_filter\(\);", ext0, re.M):
        fails.append("install_notify_filter() is called: it patches the same winmm function as install_msg_hook (0x18000BC00) - the send-hook bug class")
    # 3. the runtime registry must see every installer: no raw VirtualProtect bypassing the t2r_vprot wrapper outside the header that defines it
    ext = open(os.path.join(EXT, "t2r-ext.c"), "rb").read().decode("utf-8", "replace")
    if "#define VirtualProtect(a, n, p, o) t2r_vprot(" not in ext:
        fails.append("t2r-ext.c no longer routes VirtualProtect through t2r_vprot (the hook registry sees nothing)")
    first_use = ext.find("VirtualProtect(")
    macro = ext.find("#define VirtualProtect(a, n, p, o)")
    if 0 <= first_use < macro and not ext[first_use - 40:first_use + 5].count("t2r_vprot") and ext[first_use:first_use + 15] != "VirtualProtect(":
        fails.append("VirtualProtect used before the wrapper macro")
    # 4. every installer failure line carries the HOOK prefix (hook_miss / hook_fail), not a bare xlog: ab_asserts greps 'HOOK CONFLICT|HOOK FAIL'
    bad_re = re.compile(r'\bxlog\("[^"]*(prologue mismatch|prologue differs|not installed|exe build differs|call site differs|site differs|not hooked|NOT hooked)', re.I)
    for f in src_files():
        for no, ln in enumerate(open(f, "rb").read().decode("utf-8", "replace").split("\n"), 1):
            if bad_re.search(ln) and not any(w in ln for w in PLAIN_OK):
                fails.append("bare xlog failure line (use hook_miss / hook_fail): %s:%d: %s" % (os.path.basename(f), no, ln.strip()[:120]))
    # 5. the SendEvent regression that started this (test_send_hook_unique.py, kept as a precise check)
    inst = len(re.findall(r"uint8_t \*f = \(uint8_t \*\)VMA\(0x18005DC60\);", ext))
    if inst != 1:
        fails.append("expected exactly 1 entry patcher of 0x18005DC60 (winmm SendEvent), found %d" % inst)
    # 6. the extractor itself still catches an overlap (a synthetic pair), and the runtime registry (hookreg.h) behaves (C harness)
    if not overlaps([("winmm", 100, 116, "inst_a", "x:1"), ("winmm", 108, 124, "inst_b", "x:2")]):
        fails.append("self-test: overlaps() missed two installers on overlapping bytes")
    if overlaps([("winmm", 100, 116, "inst_a", "x:1"), ("exe", 100, 116, "inst_b", "x:2"), ("winmm", 116, 120, "inst_c", "x:3"), ("winmm", 104, 108, "inst_a", "x:4")]):
        fails.append("self-test: overlaps() reported modules / adjacent ranges / the same installer")
    gcc = shutil.which("gcc")
    if not gcc:
        root = os.path.dirname(TOOLS)
        for _ in range(5):      # the MSYS2 toolchain is not tracked: look in this checkout and the main checkout above a worktree
            c = os.path.join(root, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
            if os.path.exists(c):
                gcc = c
                break
            root = os.path.dirname(root)
    if gcc and sys.platform == "win32":
        tmp = tempfile.mkdtemp(prefix="t2r-hookreg-")
        try:
            exe = os.path.join(tmp, "hrh.exe")
            env = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ.get("PATH", ""), TMP=tmp, TEMP=tmp)
            r = subprocess.run([gcc, "-std=gnu2x", "-O1", "-o", exe, os.path.join(HERE, "hookreg_harness.c")], capture_output=True, text=True, env=env)
            if r.returncode:
                fails.append("hookreg_harness.c does not build: " + r.stderr[-400:])
            else:
                r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
                if r.returncode:
                    fails.append("hookreg.h harness failed:\n" + r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("note: no gcc / not Windows - the hookreg.h C harness was skipped")
    if fails:
        print("FAIL\n" + "\n".join(fails))
        return 1
    print("ok: %d static patch targets (%d dynamic), no two installers overlap, %d winmm patches checked" % (len(static), len(dynamic), len(wp)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
