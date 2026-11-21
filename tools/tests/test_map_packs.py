"""Offline tests for DLC map packs (tools/map_packs.py + the daemon's map pool / vote / 0xC6 op).
Run: python tools/tests/test_map_packs.py   (plain python; no network, no tools/t2r.db)."""
import os as _os_mt
_os_mt.environ.setdefault("T2R_MAX_TEAM", "0")   # the max-team filter has its own test (test_max_team.py)
import importlib, json, os, struct, sys, tempfile
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
BASE = ["to1-forest", "to1-gas-station", "to1-school", "to1-shipyard", "to1-resort", "to1-seraphite-camp",
        "to1-jesse-houses", "to1-custom-map-1"]
for k in ("T2R_SP_MAPS", "T2R_MAP_POOL", "T2R_MAP", "T2R_MAP_PACKS", "T2R_MAP_PACKS_FILE"):
    os.environ.pop(k, None)
tmp = tempfile.mkdtemp()

def write_reg(packs):
    p = os.path.join(tmp, "reg%d.json" % len(os.listdir(tmp)))
    json.dump({"packs": packs}, open(p, "w"))
    return p

def load_daemon(flag, reg=None, sp=""):
    os.environ["T2R_MAP_PACKS"] = flag
    if reg:
        os.environ["T2R_MAP_PACKS_FILE"] = reg
    else:
        os.environ.pop("T2R_MAP_PACKS_FILE", None)
    if sp:
        os.environ["T2R_SP_MAPS"] = sp
    else:
        os.environ.pop("T2R_SP_MAPS", None)
    import daemon
    d = importlib.reload(daemon)
    d.DB_PATH = os.path.join(tmp, "daemon.db")
    return d

def report(d, token, hashes):
    pl = token.encode() + bytes([len(hashes)]) + b"".join(struct.pack("<I", h) for h in hashes)
    fr = d.map_packs_op(pl)
    ln = struct.unpack_from("<H", fr)[0]
    return fr[2], dict(kv.split("=", 1) for kv in fr[3:2 + ln].decode().split())

# ------------------------------------------------------------------ zero entries change nothing
d = load_daemon("0")
ref_maps, ref_pool = list(d.MAPS), d.map_pool()
check([m[2] for m in ref_maps][:8] == BASE and len(ref_maps) == 25, "flag off: the 8 base maps first, list padded to PACK_BASE with the SP-section maps (Train Station is always on)")
d = load_daemon("1", write_reg([]))
check(d.MAPS == ref_maps and d.map_pool() == ref_pool and d.map_pool([A, B]) == ref_pool, "flag on, empty registry: same list and pool")
check(not d.PACKS.maps(), "empty registry: no pack maps")
d = load_daemon("1")      # the shipped tools/map_packs.json (empty)
check(d.MAPS == ref_maps, "shipped registry file: no change")
d = load_daemon("1", os.path.join(tmp, "missing.json"))
check(d.MAPS == ref_maps, "missing registry file: no change")
d = load_daemon("1", write_reg([]), sp="all")
ref_sp = list(d.MAPS)
d0 = load_daemon("0", sp="all")
check(d0.MAPS == ref_sp, "T2R_SP_MAPS=all + empty registry: same 13 maps as without the flag")

# ------------------------------------------------------------------ registry parsing
import map_packs
reg = write_reg([
    {"id": "part1-a", "ver": 1, "hash": "1a2b3c4d", "maps": [["Bill's Town", "p1-bills-town", "to1-p1-bills-town", 12],
                                                             ["Lakeside", "p1-lakeside", "to1-p1-lakeside", 10]]},
    {"id": "part1-a", "ver": 2, "hash": "deadbeef", "maps": [["Dup", "dup", "to1-p1-dup", 8]]},          # duplicate id
    {"id": "part1-b", "ver": 1, "hash": "zz", "maps": [["Bad", "bad", "to1-p1-bad", 8]]},                 # bad hash
    {"id": "part1-c", "ver": 1, "hash": "0badf00d", "maps": [["Dam", "p1-dam", "to1-p1-dam", 9]]},
    {"id": "part1-d", "ver": 1, "hash": "00000001", "maps": [["Dam again", "x", "to1-p1-dam", 9]]},      # level taken
])
packs = map_packs.load_registry(reg)
check([p["id"] for p in packs] == ["part1-a", "part1-c"], "registry: duplicates / bad hashes / taken levels dropped")
bad = os.path.join(tmp, "bad.json"); open(bad, "w").write("{not json")
check(map_packs.load_registry(bad) == [], "broken registry file = no packs")
check(map_packs.parse_report(A.encode()) is None and map_packs.parse_report(b"x" * 65) is None, "short / non-hex report refused")

# ------------------------------------------------------------------ pool = intersection of the players' packs
d = load_daemon("1", reg)
lv = [m[2] for m in d.MAPS]
PB = map_packs.PACK_BASE                      # first pack map index (= built-in + SP-section maps)
check(len(d.MAPS) == PB + 3 and lv[:8] == BASE and lv[PB:] == ["to1-p1-bills-town", "to1-p1-lakeside", "to1-p1-dam"],
      "pack maps at the fixed indices PACK_BASE.. (list padded with the SP maps)")
check(d.RESPAWNS["to1-p1-bills-town"] == 12 and d.RESPAWNS["to1-p1-dam"] == 9, "respawn counts from the registry")
sp_idx = set(range(8, PB))
check(not (set(d.map_pool()) & sp_idx), "padding SP maps stay out of the pool (T2R_SP_MAPS off)")
check(d.map_pool() == ref_pool and d.map_pool([A, B]) == ref_pool, "nobody reported: pool = the base pool")
code, r = report(d, A, [0x1a2b3c4d, 0x0badf00d])
check(code == 0xC7 and r["on"] == "1" and r["acc"] == "part1-a,part1-c" and r["pm%d" % PB] == "to1-p1-bills-town"
      and r["pm%d" % (PB + 2)] == "to1-p1-dam", "0xC7: accepted packs + pack map indices (%s)" % r)
check(d.map_pool([A]) == ref_pool + [PB, PB + 1, PB + 2], "solo with both packs: every pack map")
check(d.map_pool([A, B]) == ref_pool, "B has nothing (old client): no pack map")
code, r = report(d, B, [0x1a2b3c4d])
check(d.map_pool([A, B]) == ref_pool + [PB, PB + 1], "A has a+c, B has a: only pack a's maps")
code, r = report(d, C, [0x0badf00e])
check(r["acc"] == "-" and d.map_pool([A, B, C]) == ref_pool, "wrong hash (other version) = no pack")
check(d.map_pool() == ref_pool, "no players: no pack map")
for _ in range(60):
    opts = d.vote_options(players=[A, B, C])
    if any(i >= PB for i in opts):
        break
check(not any(i >= PB for i in opts), "vote options never offer a pack map C lacks")
os.environ["T2R_MAP"] = "to1-p1-dam"
check(d.map_index([A, C]) < PB, "forced pack map, a player lacks it: falls back to the pool")
d.MATCH_MAP.clear()
check(d.map_index([A]) == PB + 2, "forced pack map, everyone has it: that map")
os.environ.pop("T2R_MAP")
code, r = report(d, B, [])
check(d.map_pool([A, B]) == ref_pool, "a new report replaces the old one")
os.environ["T2R_MAP_PACKS"] = "0"
code, r = report(d, A, [0x1a2b3c4d])
check(r == {"on": "0"}, "flag off at runtime: on=0")

# ------------------------------------------------------------------ ext constants agree
src = open(os.path.join(TOOLS, "ext", "t2r-ext.c"), encoding="utf-8").read()
check("#define MF_NMAPS %d" % map_packs.PACK_BASE in src, "t2r-ext MF_NMAPS == map_packs.PACK_BASE")
check("#define PACK_MAPS_MAX %d" % map_packs.MAX_PACK_MAPS in src, "t2r-ext PACK_MAPS_MAX == map_packs.MAX_PACK_MAPS")
check("#define PACKS_MAX %d" % map_packs.MAX_PACKS in src, "t2r-ext PACKS_MAX == map_packs.MAX_PACKS")
check("clan_send(0x%X," % map_packs.OP_REPORT in src and "== 0x%X)" % map_packs.OP_REPLY in src, "t2r-ext sends 0xC6, parses 0xC7")
check("#define PACK_BASE_IDX %d" % map_packs.PACK_BASE in src, "t2r-ext PACK_BASE_IDX == map_packs.PACK_BASE")

print("\n%d FAILED" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
