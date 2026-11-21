"""Offline tests of the SP-parity changes (re/sp-parity.md).

  1. mesh-audio-config.bin (dc_data_patches.make_mesh_audio_overlay + mesh_audio_add): the bag-foley entries of the TAB prop variants and the
     rigged WLF bags are in the map with the source's prefix, the keys stay sorted, every game entry is unchanged (the Rattler helmet's
     gas-mask byte aside), and dconstruct parses the result (when its build is there).
  2. tools/ext/sp_parity.c, own foley: compiled with stubs into a test DLL and run against a fake Player / EffectControl: our "mlb-" configs
     are swapped to "abby-" copies (same mesh sid, other fields untouched), other prefixes / backpack configs stay, the swap is idempotent,
     t2r-sp-ownsteps-off.txt restores the engine's pointers, a wrong vtable or a count over 20 leaves everything alone.
  3. The abby set covers the mlb set: every sfx-mlb-* step / hand / body-fall event with an sfx-abby-* twin is in the same bank (the
     prefix swap cannot load-gate a sound), from tools/sp_parity/bank_index.tsv when it has been built.
Run: python tools/tests/test_sp_parity.py   (plain python; needs the game DC files in re/gamebin of the main checkout for 1, the msys2
gcc of tools/win/ext for 2; no game)."""
import ctypes, os, struct, subprocess, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path[:0] = [TOOLS, os.path.join(TOOLS, "features")]

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


# ---------------------------------------------------------------- 1. mesh-audio-config
def test_mesh_audio():
    gb = find("re", "gamebin", "dc1")
    if not gb or not os.path.exists(os.path.join(gb, "mesh-audio-config.bin")):
        print("skip mesh-audio-config (no re/gamebin/dc1)")
        return
    import dcfile
    import dc_data_patches as P
    out = tempfile.mkdtemp(prefix="t2r-spp-")
    P.make_mesh_audio_overlay(gb, out)
    raw = open(os.path.join(gb, "mesh-audio-config.bin"), "rb").read()
    new = open(os.path.join(out, "mesh-audio-config.bin"), "rb").read()

    def table(b):
        f = dcfile.DcFile(b)
        n_ent, ent = struct.unpack_from("<IQ", f.data, 20)
        rows = {r[0]: r for r in (struct.unpack_from("<QQQ", f.data, ent + 24 * k) for k in range(n_ent))}
        rec = rows[dcfile.fnv("*mesh-audio-config*")][2]
        n, kp, vp = struct.unpack_from("<QQQ", f.data, rec)
        keys = struct.unpack_from("<%dQ" % n, f.data, kp)
        vals = struct.unpack_from("<%dQ" % n, f.data, vp)
        return f, dict(zip(keys, vals)), list(keys)

    def cs(f, p):
        return bytes(f.data[p:f.data.index(b"\0", p)]).decode() if p else ""

    f0, m0, _ = table(raw)
    f1, m1, k1 = table(new)
    want = P.sp_bag_foley_meshes() if P.SP_BAG_FOLEY else {}
    check(k1 == sorted(k1), "mesh-audio-config keys sorted (binary search)")
    check(len(m1) == len(m0) + len([w for w in want if dcfile.fnv(w) not in m0]), f"entries {len(m0)} -> {len(m1)}")
    for mesh, src in want.items():
        v, s = m1.get(dcfile.fnv(mesh)), m0[dcfile.fnv(src)]
        ok = v is not None and f1.q(v + 8) == dcfile.fnv(mesh) and cs(f1, f1.q(v + 0x10)) == cs(f0, f0.q(s + 0x10)) \
            and cs(f1, f1.q(v)) == mesh and f1.q(v - 8) == dcfile.fnv("mesh-audio-config")
        check(ok, f"{mesh}: prefix {cs(f0, f0.q(s + 0x10))} from {src}")
    bad = []
    for k, v0 in m0.items():
        v1 = m1[k]
        for i in range(0x90 // 8):
            a, b = f0.q(v0 + 8 * i), f1.q(v1 + 8 * i)
            if f0.is_ptr(v0 + 8 * i):
                if a >= f0.strings and cs(f0, a) != cs(f1, b):
                    bad.append((k, i))
            elif a != b and not (k == dcfile.fnv("slaver-male-helmet-02") and i == 3):
                bad.append((k, i))
    for mesh, src in (P.SP_BAG_FOLEY_PREFIX.items() if P.SP_BAG_FOLEY else []):
        v, s = m1[dcfile.fnv(mesh)], m1[dcfile.fnv(src)]
        check(cs(f1, f1.q(v + 0x10)) == cs(f1, f1.q(s + 0x10)), f"{mesh}: prefix now {src}'s {cs(f1, f1.q(s + 0x10))}")
        bad = [x for x in bad if not (x[0] == dcfile.fnv(mesh) and x[1] == 2)]
    check(not bad, f"every game entry unchanged ({len(bad)} differences)")
    dcon = find("tools", "win", "ext", "dcmain", "build", "dconstruct.exe")
    if dcon:
        asm = os.path.join(out, "mac.asm")
        subprocess.run([dcon, "-i", os.path.join(out, "mesh-audio-config.bin"), "-o", asm, "--no_decompile"], capture_output=True)
        txt = open(asm, errors="replace").read() if os.path.exists(asm) else ""
        check(f"keys array" in txt and f"{{size: {len(m1)}}}" in txt, "dconstruct parses the grown map")


# ---------------------------------------------------------------- 2. own foley (sp_parity.c)
HARNESS = r'''
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define T2R_MAX_PEERS 8
#define LOGCAP(c, n) ((c)++ < (n))
#define SNLEFT(buf, n) ((size_t)(n) < sizeof(buf) ? sizeof(buf) - (size_t)(n) : (size_t)0)
#define VMA(x) ((uintptr_t)g_fake_vma + ((x) - 0x180000000ULL))
static uint8_t g_fake_vma[0x200000] __attribute__((aligned(4096)));
static uint8_t g_fake_exe[0x2b28000] __attribute__((aligned(4096)));
#define GetModuleHandleW(x) ((HMODULE)(x == NULL ? (void *)g_fake_exe : (void *)GetModuleHandleW(x)))
static int g_test_agi; static float g_test_pos[16];
static uint8_t g_puppet_dead_here[T2R_MAX_PEERS], g_peer_downed[T2R_MAX_PEERS];
static uint8_t g_test_obj[0x200];
static void *clipfx_fe_hook(void *ec, void *out, uint8_t *info) { (void)ec; (void)info; return out; }
static const struct { uint64_t sid; const char *name; } SASFX_NAMES[] = {{0x3468ca48dcde7940ULL, "gear-lower-pistol-leg-unholster"}, {0x1e3a41d7311e70e2ULL, "gear-upper-pistol-unholster"}};
#define SASFX_NK 2
static uint8_t *g_test_me;
static uint8_t g_test_ms = 6;
static volatile uint64_t g_fire_diag_until, g_fire_tick_ms;   /* t2r-ext.c globals of the fire diagnosis (spp_fire_diag) */
static void xlog(const char *fmt, ...) { (void)fmt; }
#define hook_fail(...) xlog(__VA_ARGS__)           /* hookreg.h stand-ins: the harness only compiles sp_parity.c */
#define hook_miss(p, n, ...) xlog(__VA_ARGS__)
static uint8_t *bp_me(void) { return g_test_me; }
static uint8_t match_substate(void) { return g_test_ms; }
static uint8_t *t2r_peer(uint32_t s) { (void)s; return NULL; }
static uint64_t fnv64(const char *s) { uint64_t h = 0xcbf29ce484222325ULL; while (*s) { h ^= (uint8_t)*s++; h *= 0x100000001b3ULL; } return h; }
static uint64_t dc_call(uint64_t a, int b, uint64_t *c) { (void)a; (void)b; (void)c; return 0; }
static FILE *exe_side_open(const char *n, const char *m) { return fopen(n, m); }
static void (*volatile g_cfxe_seen_cb)(const uint8_t *info);
static volatile LONG64 g_pl_snd_n, g_pl_snd_q;   /* perf30 counters of the sound request probe (t2r-ext.c) */
static float g_fs_v_sprint = 4.6f;   /* footsteps.c sprint boundary (spp_agility_quiet reads it) */
#define SK_AGILITY 7
#define LISTEN_SPRINT_MPS 4.0f
static int sk_peer(uint32_t s, int id) { (void)s; (void)id; return g_test_agi; }   /* default 0: no Agility II peer, the puppet foley mute stays off */
static const float *puppet_locator(uint64_t h, float *b) { (void)h; (void)b; return g_test_pos; }
#define fnv64_rt fnv64
#define CFXE_NAME 0xc4bcadba8e631b86ULL
typedef struct { uint64_t type; float frame; uint32_t n; const uint64_t (*pairs)[2]; } cfxe_entry;   /* clipfx.c's anim effect event (sp_parity.c reads it) */
static uint64_t cfxe_entry_name(const cfxe_entry *e) { if (!e || !e->pairs) return 0; for (uint32_t i = 0; i < e->n && i < 64; i++) if (e->pairs[i][0] == CFXE_NAME) return e->pairs[i][1]; return 0; }
#define SID_PLAYER 0x4580fab03b7eb9c0ULL
static const float *player_locator(float *b) { (void)b; return NULL; }
static int rcam_get(float *p, float *f) { (void)p; (void)f; return 0; }
static int gx_joint_pos(uint64_t h, const char *j, float *o) { (void)h; (void)j; (void)o; return 0; }
static void imm_snd_probe(uint64_t sid, uint64_t r8) { (void)sid; (void)r8; }
static void vx_snd_probe(uint64_t sid, uint64_t r8) { (void)sid; (void)r8; }
#include "sp_parity.c"
__declspec(dllexport) void t_set(uint8_t *me) { g_test_me = me; }
__declspec(dllexport) uintptr_t t_vt(void) { return (uintptr_t)GetModuleHandleW(NULL) + 0x2b27490; }
__declspec(dllexport) void t_init(void) {      /* puppet-object lookup (exe 0x18000A200) = mov rax, g_test_obj ; ret */
    uint8_t *f = g_fake_vma + 0xA200; DWORD o;
    VirtualProtect(g_fake_vma + 0xA000, 0x1000, PAGE_EXECUTE_READWRITE, &o);
    f[0] = 0x48; f[1] = 0xB8; *(uint64_t *)(f + 2) = (uint64_t)(uintptr_t)g_test_obj; f[10] = 0xC3;
    *(uint32_t *)(g_test_obj + 0x94) = 77;
}
__declspec(dllexport) void t_hook(int on) { *(uint64_t *)(g_fake_exe + 0x2b274d8) = on ? (uint64_t)(uintptr_t)clipfx_fe_hook : 0; }
__declspec(dllexport) void t_agi(int lvl, float x, float z) { g_test_agi = lvl; g_test_pos[0] = x; g_test_pos[2] = z; }
__declspec(dllexport) void t_quiet(uint32_t s, uint8_t *pec, uint64_t now) { spp_agility_quiet(s, 0x1234, pec, now); }
__declspec(dllexport) int t_state(uint32_t s) { return g_spp_agi_st[s].quiet | (g_spp_agi_st[s].soft << 1); }
__declspec(dllexport) void t_flags(uint32_t s, int dead, int downed) { g_puppet_dead_here[s] = (uint8_t)dead; g_peer_downed[s] = (uint8_t)downed; }
/* a FireEffect info: type at +0x30, owner handle {ptr, id} at +0x58 (ptr + 8 -> object, id == object + 0x94), event entry at +0x388 */
__declspec(dllexport) int t_drop(uint64_t type, uint64_t name, int other_obj) {
    static uint8_t info[0x400], hp[0x20], hp2[0x20]; static uint8_t other[0x200];
    static uint64_t pairs[1][2]; static cfxe_entry e;
    pairs[0][0] = CFXE_NAME; pairs[0][1] = name; e.type = 0; e.n = 1; e.pairs = (const uint64_t (*)[2])pairs;
    *(uint8_t **)(hp + 8) = other_obj ? other : g_test_obj; *(uint32_t *)(other + 0x94) = 99;
    *(uint8_t **)(info + 0x58) = hp; *(uint32_t *)(info + 0x60) = other_obj ? 99 : 77; (void)hp2;
    *(uint64_t *)(info + 0x30) = type; *(const cfxe_entry **)(info + 0x388) = &e;
    return spp_agility_fx_drop(info);
}
__declspec(dllexport) int t_dropk(uint64_t type, uint64_t key, uint64_t val) {      /* an event whose pair is not keyed `name` (weapon-effect: `suffix`) */
    static uint8_t info[0x400], hp[0x20]; static uint64_t pairs[2][2]; static cfxe_entry e;
    pairs[0][0] = 0x1111; pairs[0][1] = 0x2222; pairs[1][0] = key; pairs[1][1] = val; e.n = 2; e.pairs = (const uint64_t (*)[2])pairs;
    *(uint8_t **)(hp + 8) = g_test_obj; *(uint8_t **)(info + 0x58) = hp; *(uint32_t *)(info + 0x60) = 77;
    *(uint64_t *)(info + 0x30) = type; *(const cfxe_entry **)(info + 0x388) = &e;
    return spp_agility_fx_drop(info);
}
__declspec(dllexport) void t_tick(void) { spp_own_foley_tick(); }
__declspec(dllexport) int t_bag(uint8_t *ec, int restore) { return spp_swap(ec, &g_spp_mute, restore, spp_want_bag, "test bag"); }
'''


def test_own_foley():
    gcc_dir = find("tools", "win", "ext", "msys64", "ucrt64", "bin")
    if not gcc_dir:
        print("skip own foley (no msys2 gcc)")
        return
    src = os.path.join(ROOT, "tools", "ext", "sp_parity.c")
    code = open(src).read()
    check("static void spp_own_foley_tick(void)" in code, "sp_parity.c has spp_own_foley_tick")
    check("g_spp_agi_st[s].obj = NULL;" in code, "agility fx-drop state is cleared for a slot without a body (pre-mortem PT81i: stale obj pointer)")
    d = tempfile.mkdtemp(prefix="t2r-spp-")
    # (the tick is throttled to 250 ms in game: the harness compiles it with a 0 ms period)
    open(os.path.join(d, "h.c"), "w").write(HARNESS.replace('#include "sp_parity.c"', '#define SPP_TICK_MS 0\n#define SPP_FILE_MS 0\n#include "sp_parity.c"'))
    dll = os.path.join(d, "spp.dll")
    env = dict(os.environ, PATH=gcc_dir + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([os.path.join(gcc_dir, "gcc.exe"), "-std=gnu2x", "-O1", "-shared", "-I", os.path.join(ROOT, "tools", "ext"),
                        "-o", dll, os.path.join(d, "h.c")], capture_output=True, text=True, env=env)
    check(r.returncode == 0, "harness compiles" + ("" if r.returncode == 0 else ": " + r.stderr[-800:]))
    if r.returncode:
        return
    lib = ctypes.CDLL(dll)
    lib.t_vt.restype = ctypes.c_uint64
    lib.t_set.argtypes = [ctypes.c_void_p]
    keep = []

    def cstr(s):
        b = ctypes.create_string_buffer(s.encode())
        keep.append(b)
        return ctypes.addressof(b)

    def cfg(prefix, sid):
        b = (ctypes.c_uint8 * 0x90)()
        keep.append(b)
        struct.pack_into("<QQQ", b, 0, cstr("mesh"), sid, cstr(prefix) if prefix else 0)
        for i in range(4, 16):
            struct.pack_into("<Q", b, 8 * i, cstr("-cotton"))
        return b
    me = (ctypes.c_uint8 * 0x400)()
    ec = (ctypes.c_uint8 * 0x400)()
    struct.pack_into("<Q", me, 0x1c8, ctypes.addressof(ec))
    struct.pack_into("<Q", ec, 0, lib.t_vt())
    cfgs = [cfg("mlb-", 0x111), cfg("backpack-militia-", 0x222), cfg("mlb-", 0x333), cfg(None, 0x444)]
    types = [1, 3, 1, 1]
    for i, (c, t) in enumerate(zip(cfgs, types)):
        struct.pack_into("<Q", ec, 0x218 + 8 * i, ctypes.addressof(c))
        struct.pack_into("<I", ec, 0x2b8 + 4 * i, t)
    struct.pack_into("<I", ec, 0x308, len(cfgs))
    lib.t_set(ctypes.addressof(me))
    off = "t2r-sp-ownsteps-off.txt"
    if os.path.exists(off):
        os.remove(off)
    lib.t_tick()

    def slot(i):
        return struct.unpack_from("<Q", ec, 0x218 + 8 * i)[0]

    def prefix_at(p):
        s = struct.unpack_from("<Q", (ctypes.c_uint8 * 0x90).from_address(p), 0x10)[0]
        return ctypes.string_at(s).decode() if s else ""

    check(prefix_at(slot(0)) == "abby-" and prefix_at(slot(2)) == "abby-", "mlb- configs -> abby- copies")
    check(slot(0) != ctypes.addressof(cfgs[0]), "slot 0 points at a copy")
    check(slot(1) == ctypes.addressof(cfgs[1]) and slot(3) == ctypes.addressof(cfgs[3]), "backpack / empty prefixes untouched")
    cp = (ctypes.c_uint8 * 0x90).from_address(slot(0))
    check(bytes(cp[0:0x10]) == bytes(cfgs[0][0:0x10]) and bytes(cp[0x18:0x90]) == bytes(cfgs[0][0x18:0x90]),
          "copy = original except the prefix (mesh sid kept: OnPropRemoved matches it)")
    check(prefix_at(ctypes.addressof(cfgs[0])) == "mlb-", "the engine's config itself is not written")
    s0 = slot(0)
    lib.t_tick()
    check(slot(0) == s0, "idempotent (same copy on the next tick)")
    open(off, "w").close()
    try:
        lib.t_tick()
        check(slot(0) == ctypes.addressof(cfgs[0]) and slot(2) == ctypes.addressof(cfgs[2]), "opt-out file restores the engine's pointers")
    finally:
        os.remove(off)
    lib.t_tick()
    struct.pack_into("<Q", ec, 0, lib.t_vt() + 8)
    struct.pack_into("<Q", ec, 0x218, ctypes.addressof(cfgs[0]))
    lib.t_tick()
    check(slot(0) == ctypes.addressof(cfgs[0]), "foreign vtable: left alone")
    struct.pack_into("<Q", ec, 0, lib.t_vt())
    struct.pack_into("<I", ec, 0x308, 21)
    lib.t_tick()
    check(slot(0) == ctypes.addressof(cfgs[0]), "count over 20: left alone")
    # puppets' worn bag: only the type-3 "backpack-*" config goes to the empty-prefix copy, and back
    struct.pack_into("<I", ec, 0x308, len(cfgs))
    lib.t_bag.argtypes = [ctypes.c_void_p, ctypes.c_int]
    n = lib.t_bag(ctypes.addressof(ec), 0)
    check(n == 1 and slot(1) != ctypes.addressof(cfgs[1]) and prefix_at(slot(1)) == "" and slot(0) == ctypes.addressof(cfgs[0]),
          "puppet bag: the type-3 backpack config muted (empty prefix), the body configs untouched")
    lib.t_bag(ctypes.addressof(ec), 1)
    check(slot(1) == ctypes.addressof(cfgs[1]), "puppet bag: t2r-sp-puppet-bag.txt restores it")

    # ---- Agility II puppet silence (re/agility2-silence-1019.md): config pointers + the FireEffect filter
    lib.t_init()
    lib.t_quiet.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint64]
    lib.t_agi.argtypes = [ctypes.c_int, ctypes.c_float, ctypes.c_float]
    lib.t_drop.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int]
    lib.t_flags.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_int]
    lib.t_hook.argtypes = [ctypes.c_int]
    lib.t_state.argtypes = [ctypes.c_uint32]
    FOOT, GU, GL, WEAPON = 0x418f812b2f84b125, 0x07cf0d54e310e1b1, 0x1415b308f53e0acc, 0x4e5c7b07e8ce96ad
    import dcfile
    fnv = dcfile.fnv
    check(fnv("foot-effect") == FOOT and fnv("gear-effect-upper") == GU and fnv("gear-effect-lower") == GL, "event type sids = the game's (dcfile hash)")
    sp_off, spr = "t2r-agility-sprint-audible.txt", "t2r-agility-fxdrop-off.txt"
    for f in (sp_off, spr):
        if os.path.exists(f):
            os.remove(f)
    for i, c in enumerate(cfgs):
        struct.pack_into("<Q", ec, 0x218 + 8 * i, ctypes.addressof(c))
    struct.pack_into("<I", ec, 0x308, len(cfgs))
    lib.t_flags(1, 0, 0)
    now = 10000
    lib.t_hook(1); lib.t_agi(0, 0.0, 0.0); lib.t_quiet(1, ctypes.addressof(ec), now)
    check(lib.t_state(1) == 0 and slot(0) == ctypes.addressof(cfgs[0]), "no Agility II: engine configs, nothing dropped")
    check(lib.t_drop(FOOT, fnv("heel"), 0) == 0 and lib.t_drop(GU, fnv("gear-move-upper"), 0) == 0, "no Agility II: foot / cloth events pass")
    lib.t_agi(2, 0.0, 0.0); lib.t_quiet(1, ctypes.addressof(ec), now + 300)
    check(lib.t_state(1) == 3, "Agility II + FireEffect wrap: quiet + fx drop")
    check(prefix_at(slot(0)) == "abby-" and prefix_at(slot(2)) == "abby-" and slot(1) == ctypes.addressof(cfgs[1]) and slot(3) == ctypes.addressof(cfgs[3]),
          "quiet puppet: mlb- configs -> quiet abby- set (landing impact), bag / empty prefix untouched")
    check(prefix_at(ctypes.addressof(cfgs[0])) == "mlb-", "the engine's own config is not written")
    check(lib.t_drop(FOOT, fnv("heel"), 0) == 1 and lib.t_drop(FOOT, fnv("toe"), 0) == 1 and lib.t_drop(FOOT, fnv("scuff"), 0) == 1
          and lib.t_drop(FOOT, fnv("wall-body-clamber-small"), 0) == 1, "foot-effects (steps, scuffs, vault / climb touches) dropped")
    check(lib.t_drop(FOOT, fnv("dland"), 0) == 0, "landing impact (dland) let through (quiet set)")
    check(lib.t_drop(GU, fnv("gear-move-upper"), 0) == 1 and lib.t_drop(GL, fnv("gear-move-lower"), 0) == 1 and lib.t_drop(GU, fnv("gear-swish"), 0) == 1,
          "cloth rustle (gear-effect upper / lower) dropped")
    check(lib.t_drop(GL, fnv("gear-lower-pistol-leg-unholster"), 0) == 0, "sidearm draw foley kept")
    check(lib.t_drop(WEAPON, fnv("grab"), 0) == 0, "other event types untouched")
    # the hand / arm touches of vaults, climbs and crawls
    SFX = fnv("suffix"); lib.t_dropk.argtypes = [ctypes.c_uint64] * 3
    check(all(lib.t_dropk(WEAPON, SFX, fnv(n)) == 1 for n in ("wpn-pat", "wpn-lift", "wpn-grab", "wpn-brush", "prone-wpn-pat")),
          "weapon-effect hand contacts (wpn-pat / lift / grab / brush) dropped")
    check(all(lib.t_dropk(WEAPON, SFX, fnv(n)) == 0 for n in ("grab", "holster", "unholster", "clip-insert", "bolt-open")), "weapon handling weapon-effects kept")
    check(all(lib.t_drop(fnv(t), fnv("hand-pat"), 0) == 1 for t in ("hand-effect-left", "hand-effect-right", "arm-effect-left", "arm-effect-right", "body-impact-effect")),
          "hand-effect / arm-effect / body-impact-effect dropped")
    check(lib.t_drop(FOOT, fnv("heel"), 1) == 0, "another body: untouched")
    lib.t_flags(1, 1, 0)
    check(lib.t_drop(FOOT, fnv("heel"), 0) == 0, "dead body keeps its sounds")
    lib.t_flags(1, 0, 1)
    check(lib.t_drop(GU, fnv("gear-move-upper"), 0) == 0, "downed body keeps its sounds")
    lib.t_flags(1, 0, 0)
    # sprint: 6 m/s over 0.7 s
    lib.t_agi(2, 4.2, 0.0); lib.t_quiet(1, ctypes.addressof(ec), now + 1000)
    check(lib.t_state(1) & 1 and lib.t_drop(FOOT, fnv("heel"), 0) == 1, "sprinting Agility II puppet: still quiet (2013)")
    open(sp_off, "w").close()
    try:
        lib.t_agi(2, 8.4, 0.0); lib.t_quiet(1, ctypes.addressof(ec), now + 1700)
        check(lib.t_state(1) == 0 and slot(0) == ctypes.addressof(cfgs[0]) and lib.t_drop(FOOT, fnv("heel"), 0) == 0,
              "t2r-agility-sprint-audible.txt: a sprint is heard again (PT80 rule), configs restored")
        lib.t_agi(2, 8.4, 0.0); lib.t_quiet(1, ctypes.addressof(ec), now + 3000)
        check(lib.t_state(1) & 1, "... and quiet again once the sprint is over")
    finally:
        os.remove(sp_off)
    open(spr, "w").close()
    try:
        lib.t_quiet(1, ctypes.addressof(ec), now + 3300)
        check(lib.t_state(1) == 1 and prefix_at(slot(0)) == "" and lib.t_drop(FOOT, fnv("heel"), 0) == 0 and lib.t_drop(GU, fnv("gear-move-upper"), 0) == 0,
              "t2r-agility-fxdrop-off.txt: PT80 behaviour (empty-prefix mute, no event drop)")
    finally:
        os.remove(spr)
    lib.t_hook(0)
    lib.t_quiet(1, ctypes.addressof(ec), now + 3600)
    check(lib.t_state(1) == 1 and prefix_at(slot(0)) == "", "FireEffect wrap missing: falls back to the empty-prefix mute (never the audible quiet set)")
    lib.t_hook(1)
    lib.t_agi(0, 8.4, 0.0); lib.t_quiet(1, ctypes.addressof(ec), now + 3900)
    check(lib.t_state(1) == 0 and slot(0) == ctypes.addressof(cfgs[0]) and slot(2) == ctypes.addressof(cfgs[2]), "peer without Agility II again: engine configs back")


# ---------------------------------------------------------------- 2b. the MP voices' effort lines (vox/characters)
def test_vox():
    gb = find("re", "gamebin", "dc1")
    if not gb or not os.path.exists(os.path.join(gb, "vox", "characters", "any-militia-male.bin")):
        print("skip vox efforts (no re/gamebin/dc1/vox)")
        return
    import dcfile
    import dc_data_patches as P

    def lookup(f, tp, h):            # the engine's hash-table: slot = sid & (n - 1), linear probing to an empty key
        n, kp, vp = struct.unpack_from("<QQQ", f.data, tp)
        s = h & (n - 1)
        for _ in range(n):
            k = f.q(kp + 8 * s)
            if k == h:
                return f.q(vp + 8 * s), bool(f.is_ptr(vp + 8 * s))
            if k == 0:
                return None, False
            s = (s + 1) & (n - 1)
        return None, False
    for sub in ("vox", "vox-rl"):
        for name in P.SP_VOX_FILES:
            src = os.path.join(gb, sub, "characters", name + ".bin")
            if not os.path.exists(src):
                continue
            raw = open(src, "rb").read()
            new, notes = P.vox_effort_patch(raw)
            f0, f1 = dcfile.DcFile(raw), dcfile.DcFile(new)
            n_ent, ent = struct.unpack_from("<IQ", f0.data, 20)
            lost = added = wrong = 0
            for k in range(n_ent):
                _, _, p = struct.unpack_from("<QQQ", f0.data, ent + 24 * k)
                tp = f0.q(p + 0x10)
                n, kp, vp = struct.unpack_from("<QQQ", f0.data, tp)
                for i in range(n):
                    key = f0.q(kp + 8 * i)
                    if key and lookup(f1, tp, key)[0] != f0.q(vp + 8 * i):
                        lost += 1
                if n < 2:
                    continue
                for line, cands in P.SP_VOX_SUBS.items():
                    if lookup(f0, tp, dcfile.fnv(line))[0] is not None:
                        continue
                    c = next((c for c in cands if lookup(f0, tp, dcfile.fnv(c))[0] is not None), None)
                    if c is None:
                        continue
                    v, isp = lookup(f1, tp, dcfile.fnv(line))
                    added += 1
                    wrong += v != lookup(f0, tp, dcfile.fnv(c))[0] or not isp
            check(len(new) == len(raw) and not lost and added and not wrong,
                  f"{sub}/{name}: {added} effort lines added ({len(notes)} notes), {lost} old lookups changed, {wrong} wrong")


# ---------------------------------------------------------------- 3. abby twins share the mlb banks
def test_twins():
    tsv = os.path.join(TOOLS, "sp_parity", "bank_index.tsv")
    if not os.path.exists(tsv):
        print("skip twin banks (tools/sp_parity/bank_index.py not run)")
        return
    import collections
    idx = collections.defaultdict(set)
    for ln in open(tsv):
        n, _, b = ln.rstrip("\n").split("\t")
        idx[n].add(b)
    pairs = [(n, "sfx-abby-" + n[8:]) for n in idx if n.startswith("sfx-mlb-") and "sfx-abby-" + n[8:] in idx]
    other = [p for p in pairs if not idx[p[0]] & idx[p[1]]]
    check(len(pairs) > 4000 and not other, f"{len(pairs)} mlb events with an abby twin, {len(other)} in another bank")


# ---------------------------------------------------------------- 4. SPP_BP_EFFECT is fnv64("bp-effect")
def test_bp_effect_const():
    import re, dcfile
    src = open(os.path.join(TOOLS, "ext", "sp_parity.c"), "rb").read().decode("latin1")
    m = re.search(r"#define SPP_BP_EFFECT (0x[0-9a-fA-F]+)ULL", src)
    check(bool(m) and int(m.group(1), 16) == dcfile.fnv("bp-effect"), "SPP_BP_EFFECT == fnv64(\"bp-effect\") (0x%016x)" % dcfile.fnv("bp-effect"))


if __name__ == "__main__":
    test_mesh_audio()
    test_own_foley()
    test_vox()
    test_twins()
    test_bp_effect_const()
    print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
    sys.exit(1 if FAILS else 0)
