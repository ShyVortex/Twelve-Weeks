"""Offline test of tools/ext/clipfx.c clipfx_fire / clipfx_fe_hook (branch clipfx-blood-r2, re/clipfx-blood-r2-1019.md).

The head of clipfx.c (up to the SfxProcess section) is compiled with stubs into a test DLL against a FAKE exe image (EffectAnimInfo ctor, the Character
effect-info builder and the signature bytes of FireEffect / the event handler are real x86 stubs at the exe's offsets) and a fake object / EffectControl:
  1. with our clipfx_fe_hook in EffectControl's vtable slot 0x48 (always) clipfx_fire reaches FireEffect (earlier it returned 0);
  2. any other pointer outside the exe image in the slot is still refused (0);
  3. our own call is tagged by thread (g_cfxe_ours_tid): the Agility II FireEffect drop and the engine-event ring never see it, so the same call made by an
     engine job thread IS filtered / recorded - an effect of ours is neither dropped nor counted as "the engine fired it" (verdict logic, no double blood);
  4. the tag is cleared after the call; one clipfx_fire = exactly one FireEffect call (no recursion through the wrapped slot);
  5. a null object / null EffectControl / wrong builder pointer returns 0 and calls nothing.
Run: python tools/tests/test_clipfx_fire.py   (plain python; needs the msys2 gcc of tools/win/ext; no game)."""
import ctypes, os, subprocess, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def find(*rel):
    for base in (ROOT, MAIN):
        p = os.path.join(base, *rel)
        if os.path.exists(p):
            return p
    return None


HARNESS = r'''
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint8_t g_fake_exe[0x4800000 + 0x1000] __attribute__((aligned(4096)));
#define GetModuleHandleW(x) ((HMODULE)((x) == NULL ? (void *)g_fake_exe : (void *)GetModuleHandleW(x)))
#define SID_PLAYER 0x4580fab03b7eb9c0ULL
static uint64_t g_t60 = 1000;
static uint8_t g_me[0x40];
static uint8_t *bp_me(void) { return g_me; }
static void xlog(const char *fmt, ...) { (void)fmt; }
static void hook_fail(const char *fmt, ...) { (void)fmt; }
#define fnv64_rt(x) 0
#define fnv64(x) fnv64_rt(x)
static uint64_t dc_call(uint64_t sid, int n, uint64_t *a) { (void)sid; (void)n; (void)a; return 0; }   /* cfxe_joint_sid_ok (joint-locator guard, clipfx.c): no locator -> not ok */
#define VMA(x) 0
static int g_drop_calls, g_vox_calls;
static int spp_agility_vox_drop(uint8_t *obj, uint64_t name) { (void)obj; (void)name; g_vox_calls++; return 0; }
static int spp_agility_fx_drop(const uint8_t *info);
static int g_drop_answer = 1;
static int spp_agility_fx_drop(const uint8_t *info) { (void)info; g_drop_calls++; return g_drop_answer; }
#include "HEAD.c"
static int g_fire_calls; static DWORD g_fire_tid_tag;
static void *fake_fire(void *ec, void *out, uint8_t *info) { (void)ec; (void)info; g_fire_calls++; g_fire_tid_tag = g_cfxe_ours_tid; ((uint64_t *)out)[0] = 0xAA; return out; }
static uint8_t g_obj[0x2000], g_ec[0x40]; static void *g_vt[0x300], *g_evt[0x20];
static uint64_t g_pairs[1][2]; static cfxe_entry g_e;
__declspec(dllexport) void t_init(void) {
    DWORD o;
    VirtualProtect(g_fake_exe + 0x1c2e000, 0x2000, PAGE_EXECUTE_READWRITE, &o);
    VirtualProtect(g_fake_exe + 0x1b0c000, 0x1000, PAGE_EXECUTE_READWRITE, &o);
    static const uint8_t ctor[24] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x6c, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18, 0x48, 0x89, 0x7c, 0x24, 0x20, 0x41, 0x54, 0x41, 0x56};
    static const uint8_t fire[17] = {0x40, 0x53, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57, 0x48, 0x81, 0xec, 0xb8, 0x04, 0x00};
    static const uint8_t dflt[16] = {0x33, 0xd2, 0x48, 0x8d, 0x4d, 0x50, 0x41, 0xb8, 0xb0, 0x03, 0x00, 0x00, 0xe8, 0x6b, 0xcc, 0xd6};
    static const uint8_t base[14] = {0x48, 0x83, 0xec, 0x48, 0x48, 0x8b, 0x81, 0xc8, 0x01, 0x00, 0x00, 0x4d, 0x8b, 0xd8};
    static const uint8_t cend[5] = {0x41, 0x5e, 0x41, 0x5c, 0xc3}, bend[5] = {0x48, 0x83, 0xc4, 0x48, 0xc3};
    memcpy(g_fake_exe + 0x1c2ec30, ctor, 24); memcpy(g_fake_exe + 0x1c2ec30 + 24, cend, 5);
    memcpy(g_fake_exe + 0x38a260, fire, 17); memcpy(g_fake_exe + 0x1b04824, dflt, 16);
    memcpy(g_fake_exe + 0x1b0c160, base, 14); memcpy(g_fake_exe + 0x1b0c160 + 14, bend, 5);
    g_cfxe_fe_orig = fake_fire;
    *(uint64_t *)(g_fake_exe + 0x2b274d8) = (uint64_t)(uintptr_t)clipfx_fe_hook;     /* install_clipfx_hook's result */
    g_pairs[0][0] = CFXE_NAME; g_pairs[0][1] = 0x1234; g_e.type = CFXE_TYPE; g_e.n = 1; g_e.pairs = (const uint64_t (*)[2])g_pairs;
}
/* which_slot 0 = our hook, 2 = a pointer outside the image */
__declspec(dllexport) void t_setup(int which_slot, int vt508_ok) {
    *(void ***)g_obj = g_vt; *(uint8_t **)(g_obj + 0x1c8) = g_ec; *(void ***)g_ec = g_evt;
    g_vt[0x508 / 8] = vt508_ok ? (void *)(g_fake_exe + 0x1b0c160) : (void *)1;
    g_evt[0x48 / 8] = which_slot == 0 ? (void *)clipfx_fe_hook : (void *)fake_fire;
    g_fire_calls = 0; g_drop_calls = 0; g_cfxe_ours_tid = 0; g_cfxe_ri = 0; memset(g_cfxe_ring, 0, sizeof g_cfxe_ring); g_cfxe_ok = -1;
}
__declspec(dllexport) uint64_t t_fire(int null_obj, int null_ec) {
    if (null_ec) *(uint8_t **)(g_obj + 0x1c8) = NULL;
    return clipfx_fire(null_obj ? NULL : g_obj, 0x77, &g_e, 0);
}
__declspec(dllexport) int t_calls(void) { return g_fire_calls; }
__declspec(dllexport) int t_drops(void) { return g_drop_calls; }
__declspec(dllexport) uint32_t t_tag_during(void) { return g_fire_tid_tag; }
__declspec(dllexport) uint32_t t_tag_now(void) { return g_cfxe_ours_tid; }
__declspec(dllexport) uint32_t t_tid(void) { return GetCurrentThreadId(); }
__declspec(dllexport) void t_answer(int a) { g_drop_answer = a; }
__declspec(dllexport) void t_watch(int w) { g_cfxe_watch = w; }
static uint64_t hook_call(int type, int ours, uint64_t *out_first) {
    static uint8_t info[0x400], hp[0x20], other[0x200]; uint64_t out[2] = {5, 5};
    memset(info, 0, sizeof info);
    *(uint64_t *)(info + 0x30) = type ? 0x1111ULL : CFXE_TYPE; *(const cfxe_entry **)(info + 0x388) = &g_e;
    *(uint8_t **)(hp + 8) = other; *(uint32_t *)(other + 0x94) = 99; *(uint8_t **)(info + 0x58) = hp; *(uint32_t *)(info + 0x60) = 99;
    g_cfxe_ours_tid = ours ? GetCurrentThreadId() : 0;
    clipfx_fe_hook(g_ec, out, info);
    g_cfxe_ours_tid = 0;
    *out_first = out[0];
    return 0;
}
/* the engine (the tag is not ours) fires an event through the wrapped slot; type 0 = part-effect, 1 = foot-effect (any non-CFXE type); ours = 1: same call with our tag set */
__declspec(dllexport) uint64_t t_hook(int type, int ours) { uint64_t o; hook_call(type, ours, &o); return o; }
__declspec(dllexport) int t_ring(uint64_t name) { int n = 0; for (int i = 0; i < 64; i++) if (g_cfxe_ring[i].t60 && g_cfxe_ring[i].name == name) n++; return n; }
'''


def main():
    gcc_dir = find("tools", "win", "ext", "msys64", "ucrt64", "bin")
    if not gcc_dir:
        print("skip clipfx fire (no msys2 gcc)")
        return 0
    src = open(os.path.join(ROOT, "tools", "ext", "clipfx.c"), encoding="utf-8", errors="replace").read()
    cut = src.index("// ---------------------------------------------------------------- SfxProcess joint fallback")
    head = src[:cut]
    i = src.index("static uint64_t clipfx_fire(")
    body = src[i:i + 3500]
    check("(uint64_t)evt[0x48 / 8] != (uint64_t)clipfx_fe_hook" in body, "clipfx_fire's slot check names clipfx_fe_hook (the fix is in this branch)")
    d = tempfile.mkdtemp(prefix="t2r-cfx-")
    open(os.path.join(d, "head.c"), "w", newline="\n").write(head)
    open(os.path.join(d, "h.c"), "w").write(HARNESS.replace("HEAD.c", "head.c"))
    dll = os.path.join(d, "cfx.dll")
    env = dict(os.environ, PATH=gcc_dir + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([os.path.join(gcc_dir, "gcc.exe"), "-std=gnu2x", "-O1", "-shared", "-I", os.path.join(ROOT, "tools", "ext"),
                        "-o", dll, os.path.join(d, "h.c")], capture_output=True, text=True, env=env)
    check(r.returncode == 0, "harness compiles" + ("" if r.returncode == 0 else ": " + r.stderr[-1500:]))
    if r.returncode:
        return 1
    L = ctypes.CDLL(dll)
    L.t_fire.restype = ctypes.c_uint64; L.t_hook.restype = ctypes.c_uint64
    L.t_tag_during.restype = ctypes.c_uint32; L.t_tag_now.restype = ctypes.c_uint32; L.t_tid.restype = ctypes.c_uint32
    L.t_fire.argtypes = [ctypes.c_int, ctypes.c_int]
    L.t_hook.argtypes = [ctypes.c_int, ctypes.c_int]
    L.t_ring.argtypes = [ctypes.c_uint64]
    L.t_init()
    NAME = 0x1234
    # 1. our hook in the slot
    L.t_setup(0, 1); L.t_answer(1)
    r1 = L.t_fire(0, 0)
    check(r1 == 0xAA, "hook in slot 0x48: clipfx_fire reaches FireEffect and returns its result (was 0 since 10-12): %x" % r1)
    check(L.t_calls() == 1, "exactly one FireEffect call per clipfx_fire (no recursion through the wrapped slot): %d" % L.t_calls())
    check(L.t_tag_during() == L.t_tid(), "the call is tagged with our thread id while FireEffect runs")
    check(L.t_tag_now() == 0, "the tag is cleared after the call")
    check(L.t_drops() == 0, "Agility fx-drop is not asked for our own fire (the stub would have dropped it)")
    check(L.t_ring(NAME) == 0, "our own fire is not recorded in the engine ring")
    L.t_watch(1)
    L.t_fire(0, 0)
    check(L.t_ring(NAME) == 0, "watch on: ours still not recorded (the verdict logic must not count our fire as the engine's)")
    # 3. the engine thread: filtered / recorded
    L.t_setup(0, 1); L.t_watch(1); L.t_answer(1)
    o = L.t_hook(1, 0)
    check(o == 0 and L.t_calls() == 0 and L.t_drops() == 1, "engine foot-effect on a quiet Agility II puppet: dropped before FireEffect")
    L.t_answer(0)
    o = L.t_hook(1, 0)
    check(L.t_calls() == 1 and o == 0xAA, "engine foot-effect with the drop off: passes through to FireEffect")
    L.t_setup(0, 1); L.t_watch(1); L.t_answer(0)
    L.t_hook(0, 0)
    check(L.t_ring(NAME) == 1 and L.t_calls() == 1, "engine part-effect during a takedown: recorded (verdict input) and still fired")
    L.t_setup(0, 1); L.t_watch(0); L.t_answer(0)
    L.t_hook(0, 0)
    check(L.t_ring(NAME) == 0 and L.t_calls() == 1, "watch off: nothing recorded, the event still reaches FireEffect")
    L.t_setup(0, 1); L.t_watch(1); L.t_answer(1)
    o = L.t_hook(1, 1)
    check(o == 0xAA and L.t_drops() == 0, "foot-effect entered on our tag: never dropped")
    o = L.t_hook(0, 1)
    check(o == 0xAA and L.t_ring(NAME) == 0, "part-effect entered on our tag: passes through, nothing recorded")
    # 2. a foreign pointer in the slot
    L.t_watch(0)
    L.t_setup(2, 1)
    check(L.t_fire(0, 0) == 0 and L.t_calls() == 0, "an unknown pointer outside the image in the slot: refused (0), nothing called")
    # 5. null checks
    L.t_setup(0, 1)
    check(L.t_fire(1, 0) == 0 and L.t_calls() == 0, "null object: 0, nothing called")
    L.t_setup(0, 1)
    check(L.t_fire(0, 1) == 0 and L.t_calls() == 0, "null EffectControl: 0, nothing called")
    L.t_setup(0, 0)
    check(L.t_fire(0, 0) == 0 and L.t_calls() == 0, "effect-info builder outside the exe image: 0, nothing called")
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("clipfx fire tests ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
