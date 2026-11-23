"""Offline test of the CUSTOMIZE item table and profile / wire core (re/customize-1117.md).

1. customize_items.py: every part / prop is a real look2 mesh / cloth prop of the game's characters.bin (mod-built parts are
   listed in MOD_PARTS), every pak exists in re/game-files.tsv or is a mod pak, defaults are in range, tier-1 items only use
   paks the MP level loads today, tools/ext/customize_items.h is up to date.
2. customize_core.h compiled into a DLL (the code t2r-ext runs): file parse / format round trip, clamping of bad files,
   the wire message round trip, rejection of another table / version / out-of-range index, table id = the Python one.
Run: python tools/tests/test_customize_core.py   (needs the msys2 gcc of tools/win/ext, this checkout or the main one)."""
import ctypes
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", ".")
sys.path.insert(0, os.path.join(TOOLS, "features"))
sys.path.insert(0, os.path.join(TOOLS, "models"))
import customize_items as CI  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


# parts / paks the mod builds itself (not in the game data)
MOD_PARTS = {"militia-t2r-bp-rigged-11", "militia-t2r-bp-rigged-12", "scar-t2r-bp-rigged", "scar-t2r-mask01-torso",
             "scar-t2r-mask02-torso", "scar-t2r-mask03-torso"}
MOD_PARTS |= set(CI.MOD_PARTS)        # mod-built parts with their own pak (customize_items.MOD_PARTS: part -> (actor, template))
MOD_PAKS = MOD_PARTS | {"scar-t2r-mask01-kit", "scar-t2r-mask02-kit", "scar-t2r-mask03-kit"} | {a for a, _t in CI.MOD_PARTS.values()} | {a for a, _t in CI.MOD_PROPS.values()} |     set((CI.KELLIE or {}).get("paks", ()))          # (a KELLIE row may list a pak that is neither a part's nor a prop's: the tail's skeleton)


def owner_rows_checks():
    """KELLIE (the KELLIE clothing items are only visible to the owner's account, noone else sees them in the
    lists, they only see KELLIE as a locked face): the page of another account cuts a list's TRAILING hidden rows
    (customize.c cz_listed), so every owner-only clothing row must be hidden and sit at the end of its list; the face is listed
    (locked: its kind follows the account) and no other row is of that kind."""
    T = CI.table()
    seen = 0
    for (fac, sex), cats in T.items():
        for cat, rows in cats.items():
            hid = [bool(r.get("hid")) for r in rows]
            first = hid.index(True) if True in hid else len(rows)
            check(all(hid[first:]), f"{fac} {sex} {cat}: the hidden rows are the last rows of the list ({[r['label'] for r, h in zip(rows, hid) if h]})")
            for r in rows:
                kel = "KELLIE" in r["label"] or any(p.startswith("t2r-kl-") for p in r["parts"])
                if not kel:
                    check(not r.get("hid"), f"{fac} {sex} {cat} {r['label']}: only the owner's rows are hidden")
                    continue
                seen += 1
                check((r.get("unlock") or ("",))[0] == "kellie", f"{fac} {sex} {cat} {r['label']}: the owner's unlock kind")
                if cat == "face":
                    check(not r.get("hid"), f"{fac} {sex} face {r['label']}: listed for everyone (locked)")
                else:
                    check(bool(r.get("hid")), f"{fac} {sex} {cat} {r['label']}: hidden from other accounts")
    if CI.KELLIE:
        check(seen >= 10, f"owner rows found: {seen}")


def data_checks():
    T = CI.table()
    try:
        import faction_looks
        looks = faction_looks.load_looks()
    except Exception as e:            # noqa: BLE001 (no characters.bin in this checkout: skip the data part)
        print("SKIP data checks:", e)
        return
    meshes = {m for v in looks.values() for m in v["meshes"]}
    props = {m for v in looks.values() for m in v["props"]}
    tsv = os.path.join(ROOT, "re", "game-files.tsv")
    if not os.path.exists(tsv):
        tsv = os.path.join(MAIN, "re", "game-files.tsv")
    paks = {ln.split("\t")[1].split("/")[-1][:-4] for ln in open(tsv, encoding="utf-8") if "\tactor97/" in ln}
    bad_p, bad_k, bad_t1 = [], [], []
    for key, cats in T.items():
        for c, items in cats.items():
            for it in items:
                # (the rebuilt Seraphite torso rows, customize_items.PORTED: tier 2 until the data build ships PORTED_PAKS + their records)
                ported = it["tier"] >= 2 and any(k in CI.PORTED_PAKS for k in it["paks"])
                for p in it["parts"]:
                    if p not in meshes and p not in MOD_PARTS and not ported:
                        bad_p.append((key, c, it["label"], p))
                for p in it["props"]:
                    # SP coat cloth variants are paks without a look2-prop record (tier 2: the build makes the record)
                    if p not in props and p not in CI.MOD_PROPS and not (it["tier"] >= 2 and (p in paks or ported)):
                        bad_p.append((key, c, it["label"], p))
                for k in it["paks"]:
                    if k not in paks and k not in MOD_PAKS and k not in CI.PORTED_PAKS:
                        bad_k.append((key, c, it["label"], k))
                if it["tier"] == 1 and not all(k in CI.MP_PAKS_NOW for k in it["paks"]):
                    bad_t1.append((key, c, it["label"]))
    check(not bad_p, f"every part / prop exists in characters.bin {bad_p[:5]}")
    check(not bad_k, f"every pak exists (game-files.tsv or mod) {bad_k[:5]}")
    check(not bad_t1, f"tier-1 items only use paks the MP level loads today {bad_t1[:5]}")
    for key, d in CI.DEFAULTS.items():
        for c, i in d.items():
            check(i < len(T[key][c]) and T[key][c][i]["tier"] == 1, f"default {key} {c} = {i} is a tier-1 item")
    check(all(len(T[k]["torso"]) >= 3 for k in T), "every faction / sex has torso choices")
    sc = [it["label"] for it in T[("scar", "m")]["torso"]]
    check(any("RAINCOAT" in l for l in sc) and any(l.endswith("SHIRT") for l in sc), "Seraphite torso: coats + shirt-only")


def header_check():
    h = os.path.join(TOOLS, "ext", "customize_items.h")
    check(os.path.exists(h) and open(h, encoding="utf-8").read() == CI.header(), "tools/ext/customize_items.h is up to date (customize_items.py --header)")


WRAP = r'''
#define CZ_API __declspec(dllexport)
#include "customize_core.h"
__declspec(dllexport) int cz_size(void) { return (int)sizeof(cz_profile_t); }
__declspec(dllexport) int cz_get(const cz_profile_t *p, int f, int s, int c) { return c < 0 ? p->sex[f] : p->it[f][s][c]; }
__declspec(dllexport) void cz_set(cz_profile_t *p, int f, int s, int c, int v) { if (c < 0) p->sex[f] = (uint8_t)v; else p->it[f][s][c] = (uint8_t)v; }
__declspec(dllexport) int cz_wget(const cz_wire_t *w, int f, int c) { return c < 0 ? w->sex[f] : w->it[f][c]; }
__declspec(dllexport) int cz_msglen(void) { return CZ_MSG_LEN; }
static uint32_t *cz_slot(cz_profile_t *p, int f, int kind, int arg) {
    cz_fstat_t *q = &p->fs[f];
    return kind == CZK_MAPWINS ? &q->mw[arg] : kind == CZK_COUNT ? &q->cnt[arg] : kind == CZK_BEST ? &q->best[arg] : &q->st[kind];
}
// (both factions: the tests that are not about the faction split)
__declspec(dllexport) void cz_setstat(cz_profile_t *p, int kind, int arg, unsigned v) { for (int f = 0; f < CZ_NFAC; f++) *cz_slot(p, f, kind, arg) = v; }
__declspec(dllexport) unsigned cz_getstat(cz_profile_t *p, int kind, int arg) { return *cz_slot(p, 0, kind, arg); }
__declspec(dllexport) void cz_setstat_f(cz_profile_t *p, int f, int kind, int arg, unsigned v) { *cz_slot(p, f, kind, arg) = v; }
__declspec(dllexport) unsigned cz_getstat_f(cz_profile_t *p, int f, int kind, int arg) { return *cz_slot(p, f, kind, arg); }
__declspec(dllexport) int cz_item_locked(const cz_profile_t *p, int f, int s, int c, int k) { return !cz_unlocked(p, cz_item(f, s, c, k)); }
__declspec(dllexport) unsigned cz_item_progress(const cz_profile_t *p, int f, int s, int c, int k) { return cz_progress(p, cz_item(f, s, c, k)); }
'''


def core_checks():
    gcc = None
    for base in (ROOT, MAIN):
        p = os.path.join(base, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if os.path.exists(p):
            gcc = p
            break
    if not gcc:
        print("SKIP core checks: no gcc")
        return
    tmp = tempfile.mkdtemp(prefix="cztest")
    src, dll = os.path.join(tmp, "w.c"), os.path.join(tmp, "czcore.dll")
    open(src, "w").write(WRAP)
    env = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ.get("PATH", ""))
    subprocess.check_call([gcc, "-std=gnu2x", "-O2", "-Wall", "-Wno-unused-function", "-shared", "-static", "-I", os.path.join(TOOLS, "ext"),
                           "-o", dll, src], env=env)
    L = ctypes.CDLL(dll)
    P = ctypes.c_void_p
    for fn, args, res in (("cz_defaults", [P], None), ("cz_clamp", [P], ctypes.c_int), ("cz_parse", [P, ctypes.c_char_p], ctypes.c_int),
                          ("cz_format", [P, ctypes.c_char_p, ctypes.c_int], ctypes.c_int), ("cz_msg", [P, ctypes.c_uint8, ctypes.c_char_p], ctypes.c_int),
                          ("cz_recv", [ctypes.c_char_p, ctypes.c_int, P], ctypes.c_int), ("cz_table_id", [], ctypes.c_uint16),
                          ("cz_count", [ctypes.c_int] * 3, ctypes.c_int), ("cz_get", [P, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int),
                          ("cz_set", [P] + [ctypes.c_int] * 4, None), ("cz_wget", [P, ctypes.c_int, ctypes.c_int], ctypes.c_int),
                          ("cz_setstat", [P, ctypes.c_int, ctypes.c_int, ctypes.c_uint], None), ("cz_getstat", [P, ctypes.c_int, ctypes.c_int], ctypes.c_uint),
                          ("cz_setstat_f", [P, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint], None),
                          ("cz_getstat_f", [P, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_uint),
                          ("cz_item_locked", [P] + [ctypes.c_int] * 4, ctypes.c_int), ("cz_item_progress", [P] + [ctypes.c_int] * 4, ctypes.c_uint)):
        getattr(L, fn).argtypes = args
        getattr(L, fn).restype = res
    n = L.cz_size()
    a, b = ctypes.create_string_buffer(n), ctypes.create_string_buffer(n)
    T = CI.table()
    check(L.cz_table_id() == CI.table_id(), f"table id C {L.cz_table_id():04x} = Python {CI.table_id():04x}")
    for fi, fac in enumerate(CI.FACTIONS):
        for si, sex in enumerate(CI.SEXES):
            check(all(L.cz_count(fi, si, ci) == len(T[(fac, sex)][c]) for ci, c in enumerate(CI.CATS)), f"C list sizes = Python ({fac} {sex})")
    # defaults
    L.cz_defaults(a)
    check(L.cz_get(a, 0, 0, 1) == CI.DEFAULTS[("wlf", "m")]["torso"], "defaults: WLF male torso")
    # unlocks: a fresh profile has only the defaults (and both sexes, and a bare head) open
    K = {k: i + 1 for i, k in enumerate(CI.U_KINDS)}

    def setu(p, u, v):                  # the counter behind challenge u = (key, number, map)
        kind, arg = CI.U_CHAL[u[0]][:2]
        L.cz_setstat(p, K[kind], u[2] if kind == "mapwins" else arg, v)

    def open_all(p, v=100000):
        for k in CI.U_SCALAR:
            L.cz_setstat(p, K[k], 0, v)
        for m in range(len(CI.U_MAPS)):
            L.cz_setstat(p, K["mapwins"], m, v)
        for i in CI.U_LABELS:
            L.cz_setstat(p, K["count"], i, v)
            L.cz_setstat(p, K["best"], i, v)

    for fi, fac in enumerate(CI.FACTIONS):
        for si, sex in enumerate(CI.SEXES):
            for ci, c in enumerate(CI.CATS):
                for k, it in enumerate(T[(fac, sex)][c]):
                    want = 0 if (c in CI.U_NOLOCK or k == CI.DEFAULTS[(fac, sex)].get(c, 0) or it["label"] == "NONE") else 1
                    if L.cz_item_locked(a, fi, si, ci, k) != want:
                        check(False, f"fresh lock state {fac} {sex} {c} {it['label']}")
    check(True, "fresh profile: defaults + SEX + NONE open, everything else locked")
    kn = T[("wlf", "m")]["melee"][1]["unlock"]                # KNIFE: earned with the fists
    check(kn == ("melee-downs", 25, 0), f"KNIFE unlocks at 25 melee downs ({kn})")
    setu(a, kn, 24)
    check(L.cz_item_locked(a, 0, 0, 5, 1) == 1 and L.cz_item_progress(a, 0, 0, 5, 1) == 24, "24 melee downs: knife still locked, progress 24")
    setu(a, kn, 25)
    check(L.cz_item_locked(a, 0, 0, 5, 1) == 0, "25 melee downs: knife unlocked")
    # per faction: melee downs made as WLF do not open the Seraphite knife, and the other way round
    L.cz_setstat(a, K["count"], kn[0] and CI.U_CHAL[kn[0]][1], 0)
    L.cz_setstat_f(a, 0, K["count"], CI.U_CHAL[kn[0]][1], 1000)
    check(L.cz_item_locked(a, 0, 0, 5, 1) == 0 and L.cz_item_locked(a, 0, 1, 5, 1) == 0 and L.cz_item_locked(a, 1, 0, 5, 1) == 1 and L.cz_item_locked(a, 1, 1, 5, 1) == 1,
          "melee downs as WLF: the WLF knives open, the Seraphite knives stay locked")
    L.cz_setstat_f(a, 0, K["count"], CI.U_CHAL[kn[0]][1], 0)
    L.cz_setstat_f(a, 1, K["count"], CI.U_CHAL[kn[0]][1], 1000)
    check(L.cz_item_locked(a, 0, 0, 5, 1) == 1 and L.cz_item_locked(a, 1, 0, 5, 1) == 0, "melee downs as Seraphite: only the Seraphite knife opens")
    L.cz_setstat(a, K["count"], CI.U_CHAL[kn[0]][1], 0)
    # one item of each kind: below the number locked, at the number open, and only its own counter opens it
    seen = set()
    for fi, fac in enumerate(CI.FACTIONS):
        for si, sex in enumerate(CI.SEXES):
            for ci, c in enumerate(CI.CATS):
                for k, it in enumerate(T[(fac, sex)][c]):
                    u = it.get("unlock")
                    if not u or CI.U_CHAL[u[0]][0] in seen:
                        continue
                    kind = CI.U_CHAL[u[0]][0]
                    seen.add(kind)
                    L.cz_defaults(b)
                    open_all(b, 0)
                    setu(b, u, u[1] - 1)
                    lo = L.cz_item_locked(b, fi, si, ci, k)
                    setu(b, u, u[1])
                    hi = L.cz_item_locked(b, fi, si, ci, k)
                    check(lo == 1 and hi == 0 and L.cz_item_progress(b, fi, si, ci, k) == u[1],
                          f"{kind}: {it['label']} ({CI.unlock_title(u)}: {CI.unlock_text(u)}) opens at its number")
    want_kinds = set(CI.U_KINDS) - (set() if CI.KELLIE else {"kellie"})        # (the KELLIE rows exist only with their list file + paks)
    check(seen == want_kinds, f"every challenge kind is on some item ({sorted(want_kinds - seen)} missing)")
    used = {it["unlock"][0] for cats in T.values() for its in cats.values() for it in its if it.get("unlock")}
    check(used == set(CI.U_CHAL), f"every feat is on some item ({sorted(set(CI.U_CHAL) - used)} unused)")
    maps = {it["unlock"][2] for cats in T.values() for its in cats.values() for it in its if it.get("unlock") and it["unlock"][0] == "mapwins"}
    # (a win on one map sits only on the top items now - it takes about 18 matches for that map to come up and be won)
    check(maps and maps <= set(range(len(CI.U_MAPS))), f"map wins name maps of the rotation ({len(maps)} of {len(CI.U_MAPS)})")
    for key, (kind, arg, title, line, lv, lo) in CI.U_CHAL.items():
        if kind in CI.U_PLAIN:                                # not a challenge: a plain line, no number
            check(len(lv) == CI.U_NLEVEL and "%" not in line and set(lv) == {1}, f"feat {key}: a plain line, target 1")
            continue
        ok = len(lv) == CI.U_NLEVEL and line.count("%d") == 1 and line.count("%") == (2 if kind == "mapwins" else 1) and title.isupper() is not False
        ok = ok and (kind not in ("count", "best") or arg in CI.U_LABELS) and kind in CI.U_KINDS and list(lv) == sorted(lv)
        check(ok, f"feat {key}: {title} / {line}") if not ok else None
    # (a 224 character image path ended the game in the engine's image setter)
    check(all(len(CI.card_spec(c, it)[0]) + 4 <= 96 for T in CI.table().values() for c in CI.CATS for it in T[c] if CI.card_spec(c, it)),
          "every card image name is at most 96 characters")
    check(all(i < 64 for i in CI.U_LABELS) and set(CI.U_AWARD_IDS.values()) <= set(CI.U_LABELS), "counter ids fit g_mis_cnt (MIS_N 64)")
    open_all(a)                                               # everything open from here on (the round trip below wears unlocked items)
    # file round trip
    L.cz_set(a, 1, 0, -1, 1)              # Seraphites wear female
    L.cz_set(a, 1, 1, 1, 3)               # Seraphite female torso 3
    L.cz_set(a, 0, 0, 0, 2)               # WLF male hat 2
    L.cz_set(a, 0, 0, 5, 1)               # WLF male melee = knife
    buf = ctypes.create_string_buffer(16384)                  # = customize.c cz_save / cz_load
    ln = L.cz_format(a, buf, 16384)
    txt = buf.value
    check(ln > 0 and txt.startswith(b"T2RCZ1\n"), "format: header")
    check(ln < 16384 - 256, f"an all-open profile file fits the 16384 byte buffer with room ({ln} bytes)")
    check(L.cz_parse(b, txt) == 1 and bytes(a.raw) == bytes(b.raw), "parse(format(p)) == p (with stat / mapwin / count / best lines)")
    check(b"stat wlf weeks 100000" in txt and b"mapwin scar forest 100000" in txt and b"count wlf downs-bow 100000" in txt and b"best scar assists 100000" in txt,
          "format writes the progress lines, per faction")
    lk = txt.replace(b"count wlf melee-downs 100000", b"count wlf melee-downs 2")
    L.cz_parse(b, lk)
    check(L.cz_get(b, 0, 0, 5) == 0, "a worn KNIFE whose unlock is gone (edited file) -> FISTS")
    h2 = T[("wlf", "m")]["hat"][2]["unlock"]
    check(L.cz_get(b, 0, 0, 0) == 2, f"a worn item keeps its unlock: its own counter is intact (hat 2: {CI.unlock_text(h2)})")
    L.cz_defaults(b)
    L.cz_parse(b, b"T2RCZ1\ncount downs 7\nbest downs 3\ncount nosuch 9\nbest 12 4\nstat count 5\nstat streak 6\n")
    check(L.cz_getstat(b, K["count"], 1) == 7 and L.cz_getstat(b, K["best"], 1) == 3 and L.cz_getstat(b, K["streak"], 0) == 6
          and L.cz_getstat(b, K["count"], 0) == 0, "count / best / stat lines: known keys read, unknown ones skipped")
    check(b"flag " not in txt, "a fresh profile writes no flag lines (the CHALLENGES tip shows on the first CUSTOMIZE visit)")
    L.cz_parse(b, txt + b"flag chtip 1\nflag nosuch 1\nflag chtip x\n")
    f2 = ctypes.create_string_buffer(16384)
    L.cz_format(b, f2, 16384)
    check(b"flag chtip 1\n" in f2.value and b"nosuch" not in f2.value and L.cz_parse(a, f2.value) == 1 and bytes(a.raw) == bytes(b.raw),
          "flag chtip: read, written back, unknown flags dropped, round trip")
    # grant lines: an item of that label is open whatever its challenge says; unknown labels are dropped; OG / owner rows stay shut
    tl = [it["label"] for it in T[("scar", "f")]["torso"]]
    if "ISLANDER LONG COAT" in tl:
        gi = tl.index("ISLANDER LONG COAT")
        mi = [it["label"] for it in T[("wlf", "m")]["mask"]].index("BONG MASK")
        L.cz_parse(b, b"T2RCZ1\n")
        was = L.cz_item_locked(b, 1, 1, 1, gi)
        L.cz_parse(b, b"T2RCZ1\r\ngrant ISLANDER LONG COAT\r\ngrant NO SUCH ITEM\ngrant BONG MASK\nlook scar f 0 %d 0 0 0 0 0\n" % gi)
        g2, g3 = ctypes.create_string_buffer(16384), ctypes.create_string_buffer(L.cz_size())
        L.cz_format(b, g2, 16384)
        check(was == 1 and L.cz_item_locked(b, 1, 1, 1, gi) == 0 and L.cz_get(b, 1, 1, 1) == gi and b"grant ISLANDER LONG COAT\n" in g2.value
              and b"NO SUCH" not in g2.value and L.cz_item_locked(b, 0, 0, CI.CATS.index("mask"), mi) == 1 and L.cz_parse(g3, g2.value) == 1
              and L.cz_item_locked(g3, 1, 1, 1, gi) == 0, "grant lines: the item is open and stays worn, written back, unknown labels dropped, the OG row stays locked")
        L.cz_defaults(b)
    # wear lines: the worn item by label wins over the index; a file without them counts TAN RAINCOAT (CZ_LEGACY_DROP)
    sm = [it["label"] for it in T[("scar", "m")]["torso"]]
    check("TAN RAINCOAT" not in sm and sm[CI.DEFAULTS[("scar", "m")]["torso"]] == "WEATHERED RAINCOAT" and T[("scar", "m")]["torso"][0]["unlock"] is None,
          "Seraphite male torso: TAN RAINCOAT out, WEATHERED RAINCOAT = the default, free")
    check(b"\nwear scar m torso " in txt and b"\nwear wlf f mask " in txt, "format writes wear lines")
    li = sm.index("LINEN SHIRT")
    L.cz_parse(b, b"T2RCZ1\ngrant LINEN SHIRT\nlook scar m 0 %d 0 0 0 0 0\n" % (li + 1))       # (grant: a fresh profile has LINEN SHIRT locked)
    check(L.cz_get(b, 1, 0, 1) == li, "an old file (no wear lines): index of LINEN SHIRT in the list with TAN RAINCOAT -> LINEN SHIRT")
    L.cz_parse(b, b"T2RCZ1\nlook scar m 0 0 0 0 0 0 0\n")
    check(L.cz_get(b, 1, 0, 1) == CI.DEFAULTS[("scar", "m")]["torso"], "an old file wearing TAN RAINCOAT -> the default (WEATHERED RAINCOAT)")
    L.cz_parse(b, b"T2RCZ1\r\ngrant LINEN SHIRT\r\nlook scar m 0 0 0 0 0 0 0\r\nwear scar m torso LINEN SHIRT\r\nwear scar m hat NO SUCH ROW\r\n")
    check(L.cz_get(b, 1, 0, 1) == li and L.cz_get(b, 1, 0, 0) == 0, "a wear line wins over the index (CRLF); an unknown label keeps the index")
    L.cz_parse(b, b"T2RCZ1\ngrant LINEN SHIRT\nlook scar m 0 %d 0 0 0 0 0\nwear wlf m hat NONE\n" % li)
    check(L.cz_get(b, 1, 0, 1) == li, "a file with wear lines: its indexes are this build's (no legacy shift)")
    L.cz_defaults(b)
    # bad files
    check(L.cz_parse(b, b"garbage") == 0 and L.cz_get(b, 0, 0, 1) == CI.DEFAULTS[("wlf", "m")]["torso"], "bad header -> defaults")
    allstat = b"".join(b"stat %s 100000\n" % k.encode() for k in CI.U_SCALAR) + \
        b"".join(b"mapwin %s 100000\n" % m.encode() for m, _ in CI.U_MAPS) + \
        b"".join(b"count %s 100000\nbest %s 100000\n" % (v.encode(), v.encode()) for v in CI.U_LABELS.values())
    L.cz_parse(b, b"T2RCZ1\nside scar x\nlook wlf m 250 999 -4 1 1 1\nside wlf f\nlook bogus m 1 1 1 1 1 1\n" + allstat)
    check(L.cz_get(b, 0, 0, 0) == CI.DEFAULTS[("wlf", "m")]["hat"] and L.cz_get(b, 0, 0, 1) == CI.DEFAULTS[("wlf", "m")]["torso"]
          and L.cz_get(b, 0, 0, 2) == CI.DEFAULTS[("wlf", "m")]["lower"] and L.cz_get(b, 0, 0, 3) == 1, "out-of-range indexes -> default, valid ones kept")
    check(L.cz_get(b, 0, 0, -1) == 1 and L.cz_get(b, 1, 0, -1) == 0, "side lines: valid applied, bad skipped")
    L.cz_parse(b, b"T2RCZ1\r\nside wlf f\r\n")
    check(L.cz_get(b, 0, 0, -1) == 1, "CRLF file")
    # wire
    msg = ctypes.create_string_buffer(64)
    k = L.cz_msg(a, 7, msg)
    check(k == L.cz_msglen() == 4 + 2 * len(CI.CATS), f"message length {k}")
    w = ctypes.create_string_buffer(64)
    check(L.cz_recv(msg.raw[:k], k, w) == 1, "recv accepts own message")
    check(L.cz_wget(w, 1, -1) == 1 and L.cz_wget(w, 1, 1) == 3 and L.cz_wget(w, 0, 0) == 2 and L.cz_wget(w, 0, 5) == 1, "recv: worn sex + items per faction")
    bad = bytearray(msg.raw[:k]); bad[1] ^= 0xff
    check(L.cz_recv(bytes(bad), k, w) == 0, "recv rejects another item table")
    bad = bytearray(msg.raw[:k]); bad[0] = 9
    check(L.cz_recv(bytes(bad), k, w) == 0, "recv rejects another version")
    bad = bytearray(msg.raw[:k]); bad[4 + 7 + 2] = 200
    check(L.cz_recv(bytes(bad), k, w) == 0, "recv rejects an out-of-range index")
    check(L.cz_recv(msg.raw[:k - 1], k - 1, w) == 0, "recv rejects a short message")
    compose_checks(L, T)


class Part(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("hidden", ctypes.c_uint8)]


def compose_checks(L, T):
    """cz_select / cz_select_props / cz_armour_pairs / cz_pushed_name on a superset built like customize_looks.py's"""
    buf = ctypes.create_string_buffer(64)
    L.cz_pushed_name.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    for a, b in ((b"militia-male-11-torso", b"militia-arm1-11-torso"), (b"scar-female-head-11", b"scar-farm01-head-11"),
                 (b"militia-t2r-bp-rigged-11", b"militia-t2r-bp-armour-11"), (b"scar-t2r-bp-rigged", b"scar-t2r-bp-armour"),
                 (b"t2r-fh-f-h2ale-head-13", b"militia-farm01-head-13"),       # (a bare-head copy: its stock head's pushed copy)
                 (b"t2r-fh-m-h4e-head-14", b"militia-arm1-head-14")):
        check(L.cz_pushed_name(a, buf, 64) == 1 and buf.value == b, f"pushed name {a.decode()} -> {buf.value.decode()}")
    check(L.cz_pushed_name(b"slaver-vest-04-torso", buf, 64) == 0, "no pushed name for the vest")
    # the hood rows are locked out under a top without a hood, and under nothing else
    L.cz_conflict_cat.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lab = lambda fac, sex, cat: [it["label"] for it in T[(fac, sex)][cat]]
    for sex, si, coat, bare in (("m", 0, "WEATHERED RAINCOAT", "LINEN SHIRT"), ("f", 1, "WORN LEATHER RAINCOAT", "ISLANDER LONG COAT")):
        worn = bytearray(len(CI.CATS))
        hat, tor = CI.CATS.index("hat"), CI.CATS.index("torso")
        for top, want in ((coat, -1), (bare, tor)):
            worn[tor] = lab("scar", sex, "torso").index(top)
            for h in ("HOOD DOWN", "HOOD UP"):
                got = L.cz_conflict_cat(1, si, bytes(worn), hat, lab("scar", sex, "hat").index(h))
                check(got == want, f"scar {sex}: {h} under {top}: conflict category {got} (want {want})")
        # ... and a hood row still worn under such a top counts as the default row when the outfit is drawn
        L.cz_effective.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
        worn[tor] = lab("scar", sex, "torso").index(bare)
        worn[hat] = lab("scar", sex, "hat").index("HOOD UP")
        eff = ctypes.create_string_buffer(len(CI.CATS))
        L.cz_effective(1, si, bytes(worn), eff)
        check(eff.raw[hat] == CI.DEFAULTS[("scar", sex)]["hat"] and eff.raw[tor] == worn[tor], f"scar {sex}: HOOD UP under {bare} is drawn as the default headwear row")
        n = sum(L.cz_conflict_cat(0, si, bytes(bytearray(len(CI.CATS))), c, k) >= 0
                for c in range(len(CI.CATS) - 1) for k in range(len(T[("wlf", sex)][CI.CATS[c]])))
        check(n == 0, f"wlf {sex}: no row conflicts with the default outfit ({n})")
    L.cz_face_look.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    check(L.cz_face_look(b"scar-male-head-13", buf, 64) == 1 and buf.value == b"scar-male-13", "face look of a head")
    L.cz_look_name.argtypes = [ctypes.c_int] * 3 + [ctypes.c_char_p, ctypes.c_int]
    check(L.cz_look_name(1, 1, 8, buf, 64) == 1 and buf.value == b"t2r-cz-sf-8", "record name = customize_looks.look_name")

    def superset(fac, sex, extras):
        names = []
        for c in CI.CATS:
            for it in T[(fac, sex)][c]:
                if it["tier"] != 1:
                    continue
                for p in it["parts"]:
                    names.append((p, 0))
                    q = CI_pushed(p)
                    if q and (p.endswith("-torso") or "-head-" in p or "backpack" in p or "bp-rigged" in p or "hooddown" in p):    # (armour_push sources)
                        names.append((q, 1))
                for p in it.get("hide", ()):
                    names.append((p, 1))
        names += [("slaver-male-helmet-02", 1), ("slaver-vest-04-torso", 1)] + [(e, 1) for e in extras]
        seen, out = set(), []
        for nm in names:
            if nm not in seen:
                seen.add(nm); out.append(nm)
        return out

    def run(fac, sex, it, sup, tx=(), lx=()):
        fi, si = CI.FACTIONS.index(fac), CI.SEXES.index(sex)
        arr = (Part * len(sup))(*[Part(n.encode(), h) for n, h in sup])
        keep = ctypes.create_string_buffer(len(sup))
        cl = lambda xs: (ctypes.c_char_p * (len(xs) + 1))(*[x.encode() for x in xs], None)
        L.cz_select.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
        k = L.cz_select(fi, si, bytes(it), arr, len(sup), cl(list(tx)), cl(list(lx)), keep)
        return k, [(sup[i][0], sup[i][1]) for i in range(len(sup)) if keep.raw[i]], arr, keep

    # WLF male defaults: exactly the default items' parts (shown) + their pushed copies + helmet / vest; extras only from the matched looks
    d = CI.DEFAULTS[("wlf", "m")]
    it = [d.get(c, 0) for c in CI.CATS[:-1]]
    sup = superset("wlf", "m", ["wlf-t2r-bkkydex-m11", "wlf-t2r-bkkydex-m08"])
    k, kept, arr, keep = run("wlf", "m", it, sup, lx=["wlf-t2r-bkkydex-m11"])
    want = set()
    # (a worn part that another worn row hides is kept as its HIDDEN record: the default face's hat-fitted hair under hat NONE)
    hidden = {h for ci, c in enumerate(CI.CATS[:-1]) for h in T[("wlf", "m")][c][it[ci]].get("hide", ())}
    for ci, c in enumerate(CI.CATS[:-1]):
        for p in T[("wlf", "m")][c][it[ci]]["parts"]:
            want.add((p, 1 if p in hidden else 0))
            q = CI_pushed(p)
            if q and (q, 1) in sup:
                want.add((q, 1))
    want |= {("slaver-male-helmet-02", 1), ("slaver-vest-04-torso", 1), ("wlf-t2r-bkkydex-m11", 1)}
    check(k == len(kept) and set(kept) == want, f"WLF male defaults: {k} parts kept, extra {sorted(set(kept) - want)}, missing {sorted(want - set(kept))}")
    names = [n for n, _ in kept]
    check(len(names) == len(set(names)), "one record per part name")
    o, c_, m = (ctypes.c_char_p * 8)(), (ctypes.c_char_p * 8)(), (ctypes.c_int * 8)()
    L.cz_armour_pairs.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    np_ = L.cz_armour_pairs(arr, keep, len(sup), o, c_, m, 4)
    pairs = {(o[i].decode(), c_[i].decode(), m[i]) for i in range(np_)}
    # (the default face 14 is its bare-head copy: under the helmet it swaps to the STOCK head's pushed copy)
    head14 = T[("wlf", "m")]["face"][CI.DEFAULTS[("wlf", "m")]["face"]]["parts"][0]
    # (the default top 11 is its hand-tint copy when customize_items.HANDTINT is on: under the vest the STOCK torso's pushed copy)
    tor11 = T[("wlf", "m")]["torso"][CI.DEFAULTS[("wlf", "m")]["torso"]]["parts"][0]
    check(tor11 == ("t2r-wh-m-hhe-11-torso" if CI.HANDTINT_TOPS else "militia-male-11-torso"), f"default WLF male torso part: {tor11}")      # (HANDTINT_TOPS: the kit-copy shape; the tint inside the stock kits keeps the stock part)
    check((head14, "militia-arm1-head-14", 1) in pairs and (tor11, "militia-arm1-11-torso", 2) in pairs,
          f"armour pairs of the default WLF male: {sorted(pairs)}")
    # an item part the superset lacks -> -1 (old data: the pool look stays)
    k2, _, _, _ = run("wlf", "m", it, [s for s in sup if s[0] != T[("wlf", "m")]["torso"][it[1]]["parts"][0]])
    check(k2 == -1, "missing part -> -1")
    # Seraphite HOOD UP: the hood-up mesh shown, the hood-down one kept hidden (the hood switch / armour clash still find it)
    hats = [x["label"] for x in T[("scar", "m")]["hat"]]
    if "HOOD UP" in hats:
        d = CI.DEFAULTS[("scar", "m")]
        it = [d.get(c, 0) for c in CI.CATS[:-1]]
        it[0] = hats.index("HOOD UP")
        sup = superset("scar", "m", []) + [("scar-male-hoodup", 0), ("scar-male-hooddown", 1)]
        k, kept, _, _ = run("scar", "m", it, sup)
        check(("scar-male-hoodup", 0) in kept and ("scar-male-hooddown", 1) in kept and ("scar-male-hooddown", 0) not in kept,
              f"HOOD UP: {[x for x in kept if 'hood' in x[0]]}")
    # (live 191, player report: the hood-down collar on a Seraphite shirt in the match) a hood part the outfit keeps HIDDEN gets
    # no armour pair - the rig shows a pair's original whenever the vest / helmet is off. Every top without a hood, and HOOD UP under
    # a coat: no hood-down pair. The default coat + HOOD DOWN keeps its pair (hood-down copy pushed under the vest and the helmet).
    for sex in ("m", "f"):
        fi, si = 1, CI.SEXES.index(sex)
        p = "scar-male" if sex == "m" else "scar-female"
        hats = [x["label"] for x in T[("scar", sex)]["hat"]]
        tors = T[("scar", sex)]["torso"]
        d = CI.DEFAULTS[("scar", sex)]
        cases = [(k, hats.index("HOOD DOWN"), False) for k, x in enumerate(tors) if p + "-hooddown" in x.get("hide", ())]
        cases += [(d["torso"], hats.index("HOOD UP"), False), (d["torso"], hats.index("HOOD DOWN"), True)]
        bad = []
        for tk, hk, want in cases:
            it = [d.get(c, 0) for c in CI.CATS[:-1]]
            it[CI.CATS.index("torso")], it[CI.CATS.index("hat")] = tk, hk
            sup = superset("scar", sex, [])
            have = set(sup)
            for q in tors[tk]["parts"]:                     # (the top's records also when its tier keeps it off the base superset)
                for e in ((q, 0), (CI_pushed(q), 1)):
                    if e[0] and e not in have and (e[1] == 0 or e[0].endswith("-torso")):
                        sup.append(e); have.add(e)
            for e in ((p + "-hooddown", 0), (p + "-hooddown", 1), (p + "-hoodup", 0), (p + "-hoodup", 1)):
                if e not in have:
                    sup.append(e); have.add(e)
            k, kept, arr, keep = run("scar", sex, it, sup)
            o, c_, m = (ctypes.c_char_p * 8)(), (ctypes.c_char_p * 8)(), (ctypes.c_int * 8)()
            np_ = L.cz_armour_pairs(arr, keep, len(sup), o, c_, m, 4) if k > 0 else -1
            hp = [(o[i].decode(), c_[i].decode()) for i in range(max(np_, 0)) if b"hooddown" in o[i]]
            if k <= 0 or bool(hp) != want:
                bad.append((tors[tk]["label"], hats[hk], k, hp))
        check(not bad, f"scar {sex}: hood-down armour pair only where the hood-down mesh is drawn ({len(cases)} outfits): {bad}")
    # cloth props: the chosen torso's coat + its pushed copy, nothing else
    L.cz_select_props.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    pn = [b"scar-male-a-jacket-cloth", b"scar-arm1-a-jacket-cloth", b"scar-male-b-jacket-cloth", b"scar-arm1-b-jacket-cloth"]
    tors = T[("scar", "m")]["torso"]
    ka = [i for i, x in enumerate(tors) if "scar-male-a-jacket-cloth" in x["props"]]
    if ka:
        it = [0] * (len(CI.CATS) - 1)
        it[1] = ka[0]
        keep = ctypes.create_string_buffer(4)
        n = L.cz_select_props(1, 0, bytes(it), (ctypes.c_char_p * 4)(*pn), 4, keep)
        check(n == 2 and keep.raw == b"\x01\x01\x00\x00", f"props of jacket A: {keep.raw}")


def CI_pushed(p):
    if p.startswith("t2r-fh-f-h") and p[11:20] == "ale-head-":
        return "militia-farm01-head-" + p[20:]
    if p.startswith("t2r-fh-m-h") and p[11:18] == "e-head-":
        return "militia-arm1-head-" + p[18:]
    if p.startswith("t2r-wh-f-hhale-") and p.endswith("-torso"):      # (a WLF top's hand-tint copy: the stock torso's pushed copy)
        return "militia-farm01-" + p[15:]
    if p.startswith("t2r-wh-m-hhe-") and p.endswith("-torso"):
        return "militia-arm1-" + p[13:]
    if p.startswith("t2r-wh-"):                                      # (its arms: no pushed copy)
        return None
    for a, b in (("-t2r-bp-rigged", "-t2r-bp-armour"), ("-male-", "-arm1-"), ("-female-", "-farm01-")):
        if a in p:
            return p.replace(a, b, 1)
    return None


def cap_checks():
    """(live 191: every WLF outfit fell back to the pool look) the worst outfit's hide lists, all categories together, fit
    cz_select's CZ_HIDE_MAX (customize_core.h); past it the later categories' hides are cut off without a word."""
    import re
    src = open(os.path.join(TOOLS, "ext", "customize_core.h"), encoding="utf-8").read()
    cap = int(re.search(r"#define CZ_HIDE_MAX (\d+)", src).group(1))
    for (fac, sex), cats in CI.table().items():
        worst = sum(max((len(it.get("hide", ())) for it in cats[c]), default=0) for c in CI.CATS[:-1])
        check(worst <= cap, "%s %s: worst outfit hides %d entries <= CZ_HIDE_MAX %d" % (fac, sex, worst, cap))


if __name__ == "__main__":
    cap_checks()
    owner_rows_checks()
    data_checks()
    header_check()
    core_checks()
    print("FAILED: %d" % len(FAILS) if FAILS else "ALL OK")
    sys.exit(1 if FAILS else 0)
