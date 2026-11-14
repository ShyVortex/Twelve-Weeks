"""Offline tests for the SP-section map support gating (tools/map_packs.py SpSupport + the daemon's map pool / vote / 0xC8 op).
A map built from a single-player section only exists in a DLL built with it (T2R_SP_MAPS); a client without it hangs at match
state 3 when the server picks the map. Rule (same as map packs): a match's pool / vote offers an SP map only when EVERY player
reported it; an old client that never reports gets base maps only.
Run: python tools/tests/test_sp_map_support.py   (plain python; no network, no tools/t2r.db)."""
import importlib, os, struct, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]

A, B, C = tok("Alice"), tok("Bob"), tok("Carol")
for k in ("T2R_SP_MAPS", "T2R_MAP_POOL", "T2R_MAP", "T2R_MAP_PACKS", "T2R_MAP_PACKS_FILE", "T2R_SP_GATE"):
    os.environ.pop(k, None)
os.environ["T2R_MAX_TEAM"] = "0"          # base-map team-size filter off: these cases test the SP gate (max_team block below turns it on)
tmp = tempfile.mkdtemp()

def load_daemon(sp="", gate=None):
    if sp:
        os.environ["T2R_SP_MAPS"] = sp
    else:
        os.environ.pop("T2R_SP_MAPS", None)
    if gate is None:
        os.environ.pop("T2R_SP_GATE", None)
    else:
        os.environ["T2R_SP_GATE"] = gate
    import daemon
    d = importlib.reload(daemon)
    d.DB_PATH = os.path.join(tmp, "daemon.db")
    return d

def report(d, token, mask):
    fr = d.sp_support_op(token.encode() + struct.pack("<I", mask))
    if fr is None:
        return None, None
    ln = struct.unpack_from("<H", fr)[0]
    return fr[2], dict(kv.split("=", 1) for kv in fr[3:2 + ln].decode().split())

import map_packs

# ------------------------------------------------------------------ SP maps off on this server: nothing changes
d = load_daemon("")
base = d.map_pool()
# Train Station is an "always" map (No Return arena): listed even with T2R_SP_MAPS unset (fixed indices 8..),
# offered once the players report having it; without players the base pool is unchanged
check(d.sp_maps_on() == {"to1-train-station"} and len(d.MAPS) == 24 and base == list(range(8)),
      "T2R_SP_MAPS unset: Train Station on (always), base pool without reports")
check(d.map_pool([A, B]) == base, "SP maps off: players don't matter")

# ------------------------------------------------------------------ SP maps on: gated by what every player reported
d = load_daemon("all")
idx = {m[2]: i for i, m in enumerate(d.MAPS)}
on = sorted(idx[l] for l in d.sp_maps_on())
import json
spec_build = {m["key"]: m.get("build") for m in json.load(open(os.path.join(TOOLS, "maps", "sp_maps.json"), encoding="utf-8"))["maps"]}
want_on = sorted(idx["to1-" + k] for k in spec_build if spec_build[k] and "to1-" + k in idx)
retired = {idx["to1-" + k] for k in spec_build if not spec_build[k] and "to1-" + k in idx}
check(len(d.MAPS) == map_packs.PACK_BASE and on == want_on and on and not (set(on) & retired), "'all': exactly the sp_maps.json build:true maps are on (%d), the rest retired" % len(on))
check(d.map_pool() == base, "no players: base maps only")
check(d.map_pool([A, B]) == base, "nobody reported (old clients): base maps only")
bit = {l: k for k, l in enumerate([m[2] for m in d.SP_MAPS])}
full = sum(1 << bit[l] for l in d.sp_maps_on())
code, r = report(d, A, full)
check(code == 0xC9 and r["on"] == "1" and int(r["sp"], 16) == full, "0xC9 reply carries the stored mask (%s)" % r)
check(d.map_pool([A]) == sorted(base + on), "solo, DLL has every enabled SP map: base + SP pool")
check(d.map_pool([A, B]) == base, "B never reported: base maps only")
one = 1 << bit["to1-downtown"]
report(d, B, one)
check(d.map_pool([A, B]) == sorted(base + [idx["to1-downtown"]]), "A has all, B only Downtown: base + Downtown")
report(d, C, 0)
check(d.map_pool([A, B, C]) == base, "C reports an empty mask: base maps only")
for _ in range(80):
    opts = d.vote_options(players=[A, B, C])
    if any(i >= 8 for i in opts):
        break
check(not any(i >= 8 for i in opts), "vote options never offer an SP map C lacks")
report(d, C, one)
seen = set()
for _ in range(200):
    seen.update(d.vote_options(players=[A, B, C]))
check(idx["to1-downtown"] in seen and not (seen - set(base) - {idx["to1-downtown"]}), "everyone has Downtown: it can be voted, no other SP map")
os.environ["T2R_MAP"] = "to1-downtown"
d.MATCH_MAP.clear()
check(d.map_index([A, B, C]) == idx["to1-downtown"], "forced SP map, everyone has it: that map")
d.MATCH_MAP.clear()
check(d.map_index([A, B, tok("Dave")]) in base, "forced SP map, a player never reported: falls back to the base pool")
os.environ.pop("T2R_MAP")
d.MATCH_MAP.clear()

# ------------------------------------------------------------------ max_team (small maps) combined with the gate
os.environ.pop("T2R_MAX_TEAM", None)
P8 = [tok("P%d" % i) for i in range(8)]
for t in P8:
    report(d, t, full)
mt = d.sp_max_team()
if not [l for l in mt if l in idx and mt[l] < 4 and l in d.sp_maps_on()]:
    # every built SP map is 4v4: exercise the small-map filter with a synthetic 3v3 SP map (the table, not the data)
    _orig_mt = d.max_team_table
    _syn = next(l for l in sorted(d.sp_maps_on()) if l in idx and l != "to1-train-station")
    d.max_team_table = d.sp_max_team = lambda: dict(_orig_mt(), **{_syn: 3})
    mt = d.sp_max_team()
small = [l for l in mt if l in idx and mt[l] < 4 and l in d.sp_maps_on()]   # built small SP maps (base maps have their own test_max_team cases)
check(bool(small), "sp_maps.json lists small maps (max_team): %s" % small)
for lvl in small:
    n = mt[lvl]
    fits = P8[:2 * n]          # team size n
    over = P8[:2 * n + 2]      # team size n + 1
    check(idx[lvl] in d.map_pool(fits) if lvl in d.sp_maps_on() else True, "%s (max_team %d) is in the pool for a %dv%d match" % (lvl, n, n, n))
    check(idx[lvl] not in d.map_pool(over), "%s (max_team %d) is out of the pool for a bigger match" % (lvl, n))
    check(idx[lvl] not in d.map_pool(over) and d.map_pool(over), "the pool for a bigger match is never empty (base / big maps stay)")
    os.environ["T2R_MAP"] = lvl        # a forced map ignores max_team on purpose (test_max_team: "forces it even for 8 players (testing)")
    d.MATCH_MAP.clear()
    check(d.map_index(over) == idx[lvl], "forced %s: taken even for a bigger match (testing), still gated by the reports" % lvl)
    os.environ.pop("T2R_MAP")
    d.MATCH_MAP.clear()
# every player reported everything but the pool would be EMPTY for the main filter: the fallback stays on base + non-SP maps
os.environ["T2R_MAP_POOL"] = ",".join(small)
check(set(d.map_pool(P8)) <= set(range(8)) and d.map_pool(P8), "T2R_MAP_POOL names only small maps, match too big: falls back to the base maps")
os.environ.pop("T2R_MAP_POOL")
for t in P8:
    d.SPSUP.have.pop(t, None)

# ------------------------------------------------------------------ report parsing / expiry / mask range
check(map_packs.parse_sp_report(A.encode()) is None and map_packs.parse_sp_report(b"x" * 68) is None, "short / non-hex report refused")
code, r = report(d, A, 0xFFFFFFFF)
check(int(r["sp"], 16) == (1 << map_packs.SP_MAX) - 1, "mask clamped to SP_MAX bits")
now = [1000.0]
sup = map_packs.SpSupport(["to1-a", "to1-b"], clock=lambda: now[0])
sup.report(A, 1)
check(sup.allowed("to1-a", [A]) and not sup.allowed("to1-b", [A]) and sup.allowed("to1-forest", [A]), "per-bit support, non-SP maps always")
now[0] += map_packs.REPORT_TTL + 1
check(not sup.allowed("to1-a", [A]), "a report older than REPORT_TTL no longer counts")

# ------------------------------------------------------------------ gating switch off (testing an old DLL)
d = load_daemon("all", gate="0")
code, r = report(d, A, 0)
check(r == {"on": "0"}, "T2R_SP_GATE=0: on=0")
check(set(on) <= set(d.map_pool([A])), "T2R_SP_GATE=0: SP maps offered without any report")
d = load_daemon("")

# ------------------------------------------------------------------ the ext and the daemon agree
src = open(os.path.join(TOOLS, "ext", "t2r-ext.c"), encoding="utf-8").read()
check("clan_send(0x%X," % map_packs.SP_OP_REPORT in src and "== 0x%X)" % map_packs.SP_OP_REPLY in src, "t2r-ext sends 0xC8, parses 0xC9")
check("#define SP_BASE_IDX %d" % map_packs.SP_BASE in src, "t2r-ext SP_BASE_IDX == map_packs.SP_BASE")
d = load_daemon("all")
for k, (name, img, lvl, key) in enumerate(d.SP_MAPS):
    check(("{\"%s\", \"%s\"}" % (name, img)) in src and lvl == "to1-" + img.replace("outpost", "outpost"),
          "ext MF_MAPS carries %s and its level is to1-<image key> (the scan builds the level from the image key)" % name)
    check(d.MAPS[map_packs.SP_BASE + k][2] == lvl, "daemon list index %d == SP_MAPS[%d] (%s)" % (map_packs.SP_BASE + k, k, lvl))
d = load_daemon("")

# ------------------------------------------------------------------ the baked build mask (primary source in the ext)
sys.path.insert(0, os.path.join(TOOLS, "features"))
import sp_maps_build
spec = {m["key"]: m for m in sp_maps_build.specs()}
daemon_keys = [m[3] for m in d.SP_MAPS]
check(all(spec[k]["index"] == map_packs.SP_BASE + i for i, k in enumerate(daemon_keys) if k in spec),
      "sp_maps.json 'index' == daemon SP_MAPS position + SP_BASE for every listed map")
check(sp_maps_build.SP_BASE == map_packs.SP_BASE, "sp_maps_build.SP_BASE == map_packs.SP_BASE")
check(sp_maps_build.built_mask([]) == 0, "no map selected: mask 0")
downtown = [spec["downtown"]]
check(sp_maps_build.built_mask(downtown) == 1 << (spec["downtown"]["index"] - map_packs.SP_BASE), "Downtown: its own bit")
allm = sp_maps_build.selected("all")
bits = sp_maps_build.built_mask(allm)
d = load_daemon("all")
daemon_mask = sum(1 << k for k, m in enumerate(d.SP_MAPS) if m[2] in d.sp_maps_on())
check(bits == daemon_mask, "baked mask of an 'all' build == the daemon's enabled SP maps (%04x)" % bits)
tmpdir = tempfile.mkdtemp()
real = sp_maps_build.EXT_HEADER
sp_maps_build.EXT_HEADER = os.path.join(tmpdir, "sp_maps_built.h")
sp_maps_build.write_ext_header(downtown)
txt = open(sp_maps_build.EXT_HEADER).read()
check("#define T2R_SP_BUILT_MASK 0x%04xu" % sp_maps_build.built_mask(downtown) in txt, "generated header carries the mask")
sp_maps_build.write_ext_header([])
check("0x0000u" in open(sp_maps_build.EXT_HEADER).read(), "written on a no-map build too (mask 0)")
sp_maps_build.EXT_HEADER = real
check('#include "sp_maps_built.h"' in src and "T2R_SP_BUILT_MASK" in src, "t2r-ext includes the generated header and uses the baked mask")
check("sp_runtime_mask" in src and "0x403834076bd14930ULL" in src, "t2r-ext keeps the task-find scan as a cross-check")
d = load_daemon("")

print("\n%d FAILED" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
