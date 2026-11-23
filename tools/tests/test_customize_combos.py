"""Every tier-1 outfit against a REAL characters.bin that has the t2r-cz-* records (tools/features/customize_looks.py).

For each (faction, sex): every tier-1 item with the other categories at their defaults, plus 1500 random outfits. The test runs
cz_select (customize_core.h, compiled) on the record's real superset, with extras from the matching -t2r-arm twin records like
customize_compose.c cz_match_row. It fails on: an item part missing (-1), a doubled mesh, two shown torsos or heads.
It lists every extra kept (holsters, chest rigs: expected).

  python tools/tests/test_customize_combos.py <characters.bin from a build with T2R_FACTION_LOOKS=1>
"""
import collections
import ctypes
import os
import random
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.dirname(os.path.dirname(HERE))
MAIN = os.environ.get("T2R_MAIN_ROOT", ".")
sys.path[:0] = [W + "/tools/features", W + "/tools/models", W + "/tools/tests"]
import test_customize_core as TC  # noqa
import customize_items as CI      # noqa
import customize_looks as CL      # noqa
import dc_data_patches as dp      # noqa
from dcfile import DcFile         # noqa

f = DcFile(open(sys.argv[1], "rb").read())
D = f.data
looks = dp._look_table(f)


def cstr(p):
    return bytes(D[p:D.index(b"\0", p)]).decode("latin1")


def meshes(lo):
    a, c = f.q(lo + 0xa0), struct.unpack_from("<I", D, lo + 0xa8)[0]
    out = []
    for k in range(c):
        m = f.q(a + 8 * k)
        out.append((cstr(f.q(m + 0x10)), D[m + 0x48] != 0))
    return out


names = {}
n_ent, ent = struct.unpack_from("<IQ", D, 20)
for k in range(n_ent):
    sid, t, lo = struct.unpack_from("<QQQ", D, ent + 24 * k)
    if t == dp._fnv("look2"):
        names[cstr(f.q(lo + 8))] = lo
twins = {n: [x for x, _ in meshes(lo)] for n, lo in names.items() if n.endswith("-t2r-arm")}
print("records", len(names), "twins", len(twins))
# (live 191: the WLF supersets grew to 315 / 281 parts with the per-hat hair; customize_compose.c refused every record over
# CZ_SUP_MAX = 256 and every WLF body kept the pool look. cz_select itself has no cap, so the combos below all passed.)
import re  # noqa: E402
SUP_MAX = int(re.search(r"#define CZ_SUP_MAX (\d+)", open(W + "/tools/ext/customize_compose.c", encoding="utf-8").read()).group(1))
PSUP_MAX = int(re.search(r"#define CZ_PSUP_MAX (\d+)", open(W + "/tools/ext/customize_compose.c", encoding="utf-8").read()).group(1))
CAP_FAILS = []
for n, lo in names.items():
    if n.startswith("t2r-cz-"):
        c = struct.unpack_from("<I", D, lo + 0xa8)[0]
        pc = struct.unpack_from("<I", D, lo + 0xb8)[0] if f.q(lo + 0xb0) else 0
        if c > SUP_MAX or pc > PSUP_MAX:
            CAP_FAILS.append((n, c, pc))
print("superset caps: CZ_SUP_MAX %d, CZ_PSUP_MAX %d, records over: %s" % (SUP_MAX, PSUP_MAX, CAP_FAILS or "none"))

gcc = next(p for p in (os.path.join(b, "tools/win/ext/msys64/ucrt64/bin/gcc.exe") for b in (W, MAIN)) if os.path.exists(p))
tmp = tempfile.mkdtemp(prefix="czcombo")
open(tmp + "/w.c", "w").write(TC.WRAP)
subprocess.check_call([gcc, "-std=gnu2x", "-O2", "-shared", "-static", "-I", W + "/tools/ext", "-o", tmp + "/c.dll", tmp + "/w.c"],
                      env=dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ["PATH"]))
L = ctypes.CDLL(tmp + "/c.dll")
L.cz_select.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
T = CI.table()
NW = len(CI.CATS) - 1          # the wearables (every category but SEX)
FAILS = collections.Counter()
if CAP_FAILS:
    FAILS["superset over CZ_SUP_MAX / CZ_PSUP_MAX"] = len(CAP_FAILS)
EXTRAS = collections.Counter()
ex_seen = {}


def twin_of(fac, sex, part):
    pre = ("militia-" if fac == "wlf" else "scar-")
    for n, ps in twins.items():
        if part in ps and (n.startswith(pre) or n.startswith("wlf-") == (fac == "wlf")):
            return ps
    return []


def run(fac, sex, it):
    fi, si = CI.FACTIONS.index(fac), CI.SEXES.index(sex)
    lo = names[CL.look_name(fac, sex, 0)]
    sup = meshes(lo)
    arr = (TC.Part * len(sup))(*[TC.Part(n.encode(), h) for n, h in sup])
    keep = ctypes.create_string_buffer(len(sup))
    cats = CI.CATS[:NW]
    first = lambda c: (T[(fac, sex)][c][it[cats.index(c)]]["parts"] or [""])[0]
    tx = twin_of(fac, sex, first("torso")) if "torso" in cats else []
    lx = twin_of(fac, sex, first("lower")) if "lower" in cats else []
    cl = lambda xs: (ctypes.c_char_p * (len(xs) + 1))(*[x.encode() for x in xs], None)
    k = L.cz_select(fi, si, bytes(it), arr, len(sup), cl(tx), cl(lx), keep)
    tag = "%s%s %s" % (fac, sex, [T[(fac, sex)][c][it[i]]["label"] for i, c in enumerate(cats)])
    if k <= 0:
        FAILS["-1"] += 1
        if FAILS["-1"] < 12:
            print("  -1:", tag)
        return
    kept = [sup[i] for i in range(len(sup)) if keep.raw[i]]
    shown = [n for n, h in kept if not h]
    dup = [n for n, c in collections.Counter(kept).items() if c > 1]
    if dup:
        FAILS["dup"] += 1
        print("  dup:", tag, dup)
    # a hat cut out of an NPC head keeps "-head-" in its name (t2r-hw-*, tools/models/head_hats.py) and a mask pak keeps
    # "-torso" (scar-t2r-mask*), as does a shirt's bare skin (scar-t2r-skn-*, customize_items._skn): none is a second head or torso
    tors = [n for n in shown if n.endswith("-torso") and "-t2r-mask" not in n and "-t2r-skn-" not in n]
    heads = [n for n in shown if ("-head-" in n or n.endswith("-head")) and not n.startswith("t2r-hw-")]
    # WLF female FACE 10 is the hairless head-10 copy drawn with the head-09 copy that carries the hair (customize_compose.c)
    if sorted(heads) == ["t2r-fh-f-h1ale-head-10", "t2r-fh-f-h4ale-head-09"]:
        heads = heads[:1]
    if len(tors) > 1 or len(heads) > 1:
        FAILS["2 shown"] += 1
        if FAILS["2 shown"] < 12:
            print("  two shown:", tag, tors, heads)
    items = {p for c in cats for p in T[(fac, sex)][c][it[cats.index(c)]]["parts"]}
    for n, h in kept:
        if n not in items and not n.startswith("slaver-") and "-arm1-" not in n and "-farm01-" not in n and "bp-armour" not in n:
            EXTRAS[(fac + sex, n, h)] += 1


random.seed(1)
total = 0
for (fac, sex), tab in T.items():
    if CL.look_name(fac, sex, 0) not in names:
        print("no records for", fac, sex)
        continue
    cats = CI.CATS[:NW]
    t1 = {c: [i for i, x in enumerate(tab[c]) if x["tier"] == 1] for c in cats}
    d = CI.DEFAULTS[(fac, sex)]
    base = [d.get(c, 0) for c in cats]
    for ci, c in enumerate(cats):
        for i in t1[c]:
            it = list(base)
            it[ci] = i
            run(fac, sex, it)
            total += 1
    for _ in range(1500):
        run(fac, sex, [random.choice(t1[c]) if t1[c] else 0 for c in cats])
        total += 1
print("combos", total, "fails", dict(FAILS))
print("FAILED" if FAILS else "ALL OK")
print("extras kept (faction, name, hidden): count")
for k, v in sorted(EXTRAS.items()):
    print("  ", k, v)
sys.exit(1 if FAILS else 0)
