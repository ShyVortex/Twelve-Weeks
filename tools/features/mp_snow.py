"""mp_snow.py: snow on MP characters (prototype, T2R_MP_SNOW=1 only; default builds are untouched). Analysis + evidence: re/mp-snow.md.

What ships:
  * actor97/<kit>.pak of PAKS with each listed garment material rebuilt on the snow-capable wlf-patch technique (tools/models/mp_snow_pak.py:
    the garment's textures / params re-bound into it, its overlay tint baked into the colour texture). Only paks that carry a wlf-patch
    technique themselves can be done offline today (05 / 08 / 11 / 13 kits, backpack-12); the rest need the donor grafted in (re/mp-snow.md);
  * dc1/material-param.bin overlay: SP-only material-param rows REUSED in place (a new top-level symbol / a longer row array cannot be added
    to a DC file without re-basing it). The file holds 67 g_snowStrength0N rows in 25 tables; every row is { material sid, param name ptr,
    3 floats }. Row i gets garment i's material sid (fnv64 of "<material path>:default", checked against SP: the wlf-patch sid is a row key)
    and its name pointer re-pointed at the g_snowStrength04 string (the layer index of the wlf-patch permutation), so
    set-table-shader-material-values-param(<table>, x) writes x into g_snowStrength04 of every material that table holds.
    t2r-ext mpsnow.c calls it for every table in MP_SNOW_TABLES. Wetness stays at the technique's 0.
  * tools/ext/mp_snow_built.h (generated): the ext drives the tables only when this build carries them, and which tables.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402

ON = os.environ.get("T2R_MP_SNOW") == "1"
UP, LOW, ACC, MIL = ("objects/characters/npc-normal/clothing/1upper/", "objects/characters/npc-normal/clothing/2lower/",
                     "objects/characters/npc-normal/clothing/4accessory/", "objects/characters/npc-normal/militia/upper/")
# (actor pak, garment asset name, material directory). Every garment's colour texture is used by this garment only (mp_snow_pak.build checks it).
PAKS = [
    ("militia-male-05-kit", "m-tee-10", UP), ("militia-male-05-kit", "m-shirt-05", UP),
    ("militia-male-08-kit", "m-sweater-07-b", UP), ("militia-male-08-kit", "m-vest-05-b-closed-bp", UP),
    ("militia-male-11-kit", "m-sweater-05", UP), ("militia-male-11-kit", "bandana-02", ACC),      # (m-sweater-05 = the winmm default WLF look)
    ("militia-male-13-kit", "m-tee-06", UP), ("militia-male-13-kit", "m-tee-12", UP),
    ("militia-male-13-kit", "npc-militia-m-hat-01", MIL), ("militia-male-13-kit", "holster-01", ACC),
    ("militia-male-backpack-12", "backpack-04", ACC),
]
# Cross-pak test (build flag T2R_MP_SNOW_XPAK=1; client file t2r-snow-xpak-test.txt, re/mp-snow.md 8.1): garments of paks that do NOT carry wlf-patch get its
# technique record grafted in (snow_clone.graft_record: record + strings / params / texture list / 3 shader tables, NOT the EFFECT item nor the VRAM_DESC items).
# If the engine finds the effect (hash 13acdf9c...) and the snow textures in another loaded pak (the 11 / 05 / 08 / 13 kits are always in the level) they snow
# like the others; if not they render wrong or not at all - that is the answer the test is for.
# A/B: the cross-pak material swap / graft CRASHES the loader at map load (tlou-ii.exe+1677091): the grafted technique's permutation has no EFFECT in the receiving
# pak and its donor textures no VRAM_DESC (tools/models/pak_validate.py finds both; mp_snow_pak.build refuses such paks). So:
#   T2R_MP_SNOW_XPAK=1         = IN-PAK swaps only (tools/features/data/mp-snow-inpak.json: the garment is rebuilt on a snow permutation its OWN pak already carries)
#   + T2R_MP_SNOW_XPAK_UNSAFE=1 = also the cross-pak swaps / grafts
# The graft is now COMPLETE (tools/models/pak_graft.py, re/mp-snow.md 8.19): the donor's EFFECT closure (per-pak name indices remapped), its VRAM_DESC items + trailer
# stubs, bindings inside the GEOMETRY_1 binding array, missing cbuffer layouts and a material pool slice per technique go into the receiving pak, and the result passes the strict
# pak_validate (pak_graft.check). Offline-proven only; nothing seen in game yet, so the cross-pak rows stay behind T2R_MP_SNOW_XPAK_UNSAFE=1 until one A/B map load.
INPAK_ON = os.environ.get("T2R_MP_SNOW_XPAK") == "1"
XPAK_ON = INPAK_ON and os.environ.get("T2R_MP_SNOW_XPAK_UNSAFE") == "1"
DONOR_KITS = {"militia-male-05-kit", "militia-male-08-kit", "militia-male-11-kit", "militia-male-13-kit", "militia-male-backpack-12"}
DONOR_PAK = "militia-male-11-kit"          # the donor record is read from this pak by the paks without one
XPAK = [
    ("militia-male-12-kit", "m-jacket-15", UP), ("militia-male-12-kit", "m-tee-04", UP),
    ("militia-male-14-kit", "m-jacket-06", UP), ("militia-male-14-kit", "bandana-01", ACC), ("militia-male-14-kit", "holster-01", ACC),
    ("militia-male-b-legs-kit", "m-pants-23", LOW), ("militia-male-hat-08", "cap-03", ACC), ("militia-male-backpack-08", "backpack-05", ACC),
    ("scar-male-a-jacket-kit", "scar-m-coat-a", "objects/characters/npc-normal/scars/upper/"),
]
# The wlf-patch CLONES of the kit garments (PAKS) replace the garment's own shader permutation by the generic snow one: they drop the garment's roughness / specular / stitches /
# detail layers (mp_snow_pak report: dropped_params g_roughness01, g_specular02, ...) = the plastic look (night26). The winter looks wear no cloned garment (their torsos come from
# the SP Jackson / crew parts with their own authored materials), so the clones are OFF unless T2R_MP_SNOW_CLONES=1.
CLONES_ON = os.environ.get("T2R_MP_SNOW_CLONES") == "1"
# Material swap (T2R_MP_SNOW_XPAK=1): every kit garment without a snow permutation is rebuilt on the snow-capable permutation of the CLOSEST SP winter garment of its type
# (tools/models/snow_clone.py: the garment's own textures / params are re-bound into the donor's record; the donor's cloth layers - roughness, specular, fuzz, detail - stay, unlike the generic
# wlf-patch clone), donor = (actor pak of the game, technique asset name, snow layer index its strength param carries).  Donor record + EFFECT + VRAM_DESC items + layouts are grafted
# into the pak (pak_graft.Graft via snow_clone.clone(donor_pak=...); replaces snow_clone.graft_record, which crashed the loader).  BC7 colour / mask slots get a pre-encoded BC7 .dds (mp_snow_pak.bc7_dds; were skipped before).
DONOR_TYPES = {
    "pants": ("ellie-patrol-pants", "pants", "g_snowStrength03"), "boots": ("ellie-patrol-boots", "boots", "g_snowStrength06"),
    "coat": ("ellie-patrol-jacket", "jacket", "g_snowStrength04"), "beanie": ("ellie-patrol-hoodie-hood-up", "hoodie-up-nowrinkles", "g_snowStrength04"),
    "pack": ("owen-tracking-body", "backpack", "g_snowStrength07"), "glove": ("ellie-patrol-r-glove", "gloves", "g_snowStrength03"),
    # PROP paks (-jacket-cloth cloth-sim props, -animprop: own JOINT_HIERARCHY): Ellie's "jacket" effect also reads the kind-3 / 5 cbuffers 8b2b2f71 / e1eb8a74 / 77bfcdc5, which no stock
    # prop effect uses (18 stock cloth / animprop paks: 20 ids, pak_graft.PROP_CBUFFERS) - the prop draw path does not fill them: night34 A/B, the grafted coat body (scar-male-b-jacket-cloth, scar-female-a-jacket-cloth) was
    # bright orange and stuck in bind pose on the OTHER player's screen. militia-male-02-jacket-cloth is a stock cloth pak whose wlf-patch is snow-capable with prop-safe cbuffers only.
    "coat-prop": ("militia-male-02-jacket-cloth", "wlf-patch", "g_snowStrength04"),
}
# Glow + region switching appeared on the grafted parts only: resource-list diff of the EFFECTs (pak_graft.fx_resources, tools/models/snow_donor_diff.py): the stock
# Scar / WLF materials and wlf-patch use the SAME cbuffer set (kind 0 / 1 / 3 / 5 / 6, kind-5 b38e610a 52 B = the per-character lighting block the engine fills); Ellie's jacket /
# hoodie additionally read kind-5 77bfcdc5 (68 B, instead of b38e610a) + kind-3 8b2b2f71 / e1eb8a74, Ellie's pants / boots / glove kind-3 8b2b2f71, Owen's backpack kind-3 62e7c8fd,
# which the MP draw path never fills (-> unlit / washed-out parts that switch with the light region while the stock-path coat body does not; the same unfilled-cbuffer cause as
# the orange coat). Every swap therefore uses the wlf-patch donor (stock lighting path, snow layer 04); T2R_MP_SNOW_ELLIE_DONORS=1 = the old per-type donors.
DONOR_TYPES_ELLIE = dict(DONOR_TYPES)
if os.environ.get("T2R_MP_SNOW_ELLIE_DONORS") != "1":
    DONOR_TYPES = {k: DONOR_TYPES["coat-prop"] for k in DONOR_TYPES}
_LO, _AC, _SU = "objects/characters/npc-normal/clothing/2lower/", "objects/characters/npc-normal/clothing/4accessory/", "objects/characters/npc-normal/scars/upper/"
_SH, _SL = "objects/characters/npc-normal/clothing/3shoes/", "objects/characters/npc-normal/scars/lower/"
_UP = "objects/characters/npc-normal/clothing/1upper/"
SWAP = [   # (kit actor pak, garment asset, material dir, donor type)
    ("militia-male-a-legs-kit", "m-pants-24-tuck", _LO, "pants"), ("militia-male-a-legs-kit", "boots-23", _SH, "boots"),
    ("militia-male-b-legs-kit", "m-pants-23", _LO, "pants"), ("militia-male-b-legs-kit", "boots-25-a", _SH, "boots"),
    ("militia-male-c-legs-kit", "m-pants-24-roll", _LO, "pants"), ("militia-male-c-legs-kit", "boots-27", _SH, "boots"),
    ("militia-male-d-legs-kit", "boots-21", _SH, "boots"),
    ("militia-male-backpack-05", "backpack-03", _AC, "pack"), ("militia-male-backpack-08", "backpack-05", _AC, "pack"), ("militia-male-backpack-11", "backpack-01", _AC, "pack"),
    ("militia-male-backpack-13", "backpack-02", _AC, "pack"), ("militia-male-backpack-14", "backpack-01", _AC, "pack"),
    ("militia-male-07-kit", "beanie-01", _AC, "beanie"), ("militia-male-10-kit", "beanie-01", _AC, "beanie"),
    ("scar-male-a-jacket-kit", "scar-m-coat-a", _SU, "coat"), ("scar-male-a-jacket-kit", "scar-m-shirt-01-piece", _SU, "coat"), ("scar-male-a-jacket-kit", "scar-m-hands", _SU, "glove"),
    ("scar-male-b-jacket-kit", "scar-m-coat-b", _SU, "coat"), ("scar-male-b-jacket-kit", "scar-m-shirt-03-piece", _SU, "coat"), ("scar-male-b-jacket-kit", "scar-m-hands", _SU, "glove"),
    ("scar-male-c-jacket-kit", "scar-m-coat-b", _SU, "coat"), ("scar-male-c-jacket-kit", "scar-m-shirt-01-piece", _SU, "coat"), ("scar-male-c-jacket-kit", "scar-m-hands", _SU, "glove"),
    ("scar-male-hoodup", "scar-m-coat-b", _SU, "coat"), ("scar-male-hooddown", "scar-m-coat-b", _SU, "coat"),
    ("scar-male-a-legs-kit", "scar-m-pants-03", _SL, "pants"), ("scar-male-a-legs-kit", "scar-boots", _SL, "boots"),
    ("scar-male-b-legs-kit", "scar-m-pants-01", _SL, "pants"), ("scar-male-b-legs-kit", "scar-boots", _SL, "boots"),
    ("scar-male-c-legs-kit", "scar-heavy-pants-02", _SL, "pants"), ("scar-male-c-legs-kit", "scar-boots", _SL, "boots"),
    # female pool kits (night28)
    ("militia-female-a-legs-kit", "f-pants-13-tuck-hip", _LO, "pants"), ("militia-female-a-legs-kit", "npc-militia-m-boots-01-hip", "objects/characters/npc-normal/militia/lower/", "boots"),
    ("militia-female-d-legs-kit", "boots-25-a", _SH, "boots"),
    ("militia-female-08-kit", "beanie-02", _AC, "beanie"), ("militia-female-12-kit", "beanie-02-a", _AC, "beanie"),
    ("militia-female-backpack-12", "backpack-02", _AC, "pack"), ("militia-female-backpack-13", "backpack-02", _AC, "pack"),
    # female Seraphite kits (night29; the fglv01 jacket copy takes the a-jacket-kit rows in build_dll.stage_scar_female_winter)
    ("scar-female-a-jacket-kit", "scar-f-shirt-02", _SU, "coat"), ("scar-female-a-jacket-kit", "scar-f-raincoat-a", _SU, "coat"), ("scar-female-a-jacket-kit", "scar-f-hands", _SU, "glove"),
    ("scar-female-hoodup", "scar-f-raincoat-c", _SU, "coat"), ("scar-female-hooddown", "scar-f-raincoat-c", _SU, "coat"),
    ("scar-female-a-legs-kit", "scar-f-pants-02", _SL, "pants"), ("scar-female-a-legs-kit", "scar-boots", _SL, "boots"),
    ("scar-female-b-legs-kit", "scar-f-pants-03", _SL, "pants"), ("scar-female-b-legs-kit", "scar-boots", _SL, "boots"),
    ("scar-female-backpack", "scar-heavy-backpack-01", "objects/characters/npc-normal/scars/accessories/", "pack"),
    # The female WLF blue vest look showed no snow: the remaining kit garments without a snow permutation
    ("militia-female-08-kit", "f-vest-04-b-back", _UP, "coat"), ("militia-female-08-kit", "f-sweater-07c", _UP, "coat"),
    ("militia-female-12-kit", "f-jacket-10-a", _UP, "coat"), ("militia-female-12-kit", "f-sweater-02-c", _UP, "coat"), ("militia-female-12-kit", "holster-01", _AC, "pack"),
    ("militia-female-d-legs-kit", "f-pants-11-holster-b", _LO, "pants"), ("militia-female-d-legs-kit", "holster-02-nogore", _AC, "pack"),
    ("militia-male-07-kit", "m-tee-08", _UP, "coat"), ("militia-male-07-kit", "holster-01", _AC, "pack"),
    ("militia-male-10-kit", "m-tee-06-a", _UP, "coat"), ("militia-male-10-kit", "holster-01", _AC, "pack"),
    ("militia-male-d-legs-kit", "m-pants-12-holster", _LO, "pants"), ("militia-male-d-legs-kit", "holster-02", _AC, "pack"),
    # The Scar coat body had no snow - only the arms (jacket-kit) and the hood (hoodup) were swapped: the coat body + skirt is the -jacket-cloth
    # prop pak. Audit of every game scar- / militia- pak used by the MP looks that carries a swapped material without being swapped itself:
    ("scar-male-a-jacket-cloth", "scar-m-coat-a", _SU, "coat-prop"), ("scar-male-b-jacket-cloth", "scar-m-coat-b", _SU, "coat-prop"),
    ("scar-male-c-jacket-cloth", "scar-m-coat-b", _SU, "coat-prop"), ("scar-female-a-jacket-cloth", "scar-f-raincoat-a", _SU, "coat-prop"),
    ("scar-female-hood-animprop", "scar-f-raincoat-c", _SU, "coat-prop"), ("militia-male-05-jacket-cloth", "m-shirt-05", _UP, "coat-prop"),
    ("militia-male-14-kit", "holster-01", _AC, "pack"), ("militia-female-1hmelee-holster", "f-pants-13-tuck-hip", _LO, "pants"),
    ("scar-male-backpack", "scar-heavy-backpack-01", "objects/characters/npc-normal/scars/accessories/", "pack"),
]
# The Seraphite gear was swapped on Ellie / Owen donors: orange coat (tint baked over the whole atlas, fixed: mp_snow_pak.bake adjust mask) and hood / arms /
# holster / backpack lighting differently from the coat body (unfilled donor cbuffers, see DONOR_TYPES_ELLIE above; now all donors = wlf-patch). T2R_MP_SNOW_SCAR=0 = the
# Seraphite rows off (stock materials, no snow on them).
SCAR_SWAP_ON = os.environ.get("T2R_MP_SNOW_SCAR") != "0"
if not SCAR_SWAP_ON:
    SWAP = [r for r in SWAP if not r[0].startswith("scar-")]
    XPAK = [r for r in XPAK if not r[0].startswith("scar-")]
# Every remaining row is a donor-technique swap too (offline diff: 5-29 lighting / layer params of the original material are dropped, the shader permutation is the
# donor's; see re/mp-snow.md 8.23). T2R_MP_SNOW_SWAPS=0 = no material swaps at all (stock materials everywhere, only the natively snow-capable parts keep snow).
if os.environ.get("T2R_MP_SNOW_SWAPS") == "0":
    SWAP, XPAK = [], []
# Snow vs gloss: the wlf-patch clone has no roughness / specular / metal slots, so it flattens whatever it replaces. Only the BIG visible surfaces keep a
# clone (coats, jackets, vests, sweaters, hoods, beanies / hats, backpacks); boots, pants, gloves, hands, shirt / tee pieces, holsters and the kerchief stay on their STOCK
# material with its gloss (and no snow). T2R_MP_SNOW_SMALL=1 = the old full list.
import re as _re
SMALL_RE = _re.compile(r"boots|pants|glove|hands|shirt|tee-|-piece|holster|bandana|scarf", _re.I)
SMALL_ON = os.environ.get("T2R_MP_SNOW_SMALL") == "1"


def big_surface(garment, dtype=None):
    """True = this garment keeps the snow clone (big surface); False = stock material"""
    return SMALL_ON or not (SMALL_RE.search(garment) or dtype in ("pants", "boots", "glove"))


SWAP = [r for r in SWAP if big_surface(r[1], r[3])]
XPAK = [r for r in XPAK if big_surface(r[1])]
# the mod's own copies of SWAP kits (armour twins, rigged look bags, TAB bag props) get the same swap: build_dll.stage_mp_snow_copies
COPY_RE = r"-arm1-|-farm01-|-t2r-bp-|-t2r-tab-bprop|-pushed-"      # Taking the bag off switched the bystander bag to the glossy stock material while the worn bag is the snow clone: the TAB bag props carry the SAME material swap as the worn bag again (same SWAP row, same donor, same bake). ebd23dd1 had dropped it (bag black on a bystander - the clone reads kind-3 5b6fa12f, which Abby's own prop effect set does not (it reads 8b2b2f71): if black returns, move the bag-prop clones to a donor with exactly the backpack-abby set, e.g. dina-patrol-vest)


def swap_gear_rows():
    """[(garment, material dir, donor type)] of the Jackson torso swap-gear rows that are big surfaces (their pushed armour copies take the same swap)"""
    import json
    out = []
    if XPAK_ON:
        for r in json.load(open(os.path.join(HERE, "data", "mp-snow-swap-gear.json"))):
            if big_surface(r["garment"], r["type"]):
                out.append((r["garment"], r["material"][:-len(r["garment"] + ":default")], r["type"]))
    return out
DONOR_OF = {(k, g): DONOR_TYPES[t] for k, g, _d, t in SWAP}          # (kit, garment) -> (donor pak, donor technique, strength param)
ALL = (PAKS if CLONES_ON else []) + (XPAK if XPAK_ON else []) + ([(k, g, d) for k, g, d, _t in SWAP] if XPAK_ON else [])
STRENGTH_PARAM = "g_snowStrength04"        # the layer index the wlf-patch permutation reads
HEADER = os.path.join(ROOT, "tools", "ext", "mp_snow_built.h")


def wanted():
    """[(material sid, snow param name)]: the cloned MP garments (wlf-patch layer 04) + the natively snow-capable crew parts of the winter looks
    (tools/features/data/mp-snow-crew.json: material path + the g_snowStrength0N layer its permutation reads, from tools/models/crew_winter.py's paks)"""
    out = [(fnv(d + g + ":default"), DONOR_OF[(k, g)][2] if (k, g) in DONOR_OF else STRENGTH_PARAM) for k, g, d in ALL]
    if INPAK_ON:        # in-pak swaps / native rows (mp-snow-inpak.json)
        import json
        for r in json.load(open(os.path.join(HERE, "data", "mp-snow-inpak.json"))):
            for prm in r["params"]:
                out.append((fnv(r["material"]), prm))
    if XPAK_ON:        # swapped parts of the staged winter paks (Jackson torsos, crew bits, the mask): tools/features/data/mp-snow-swap-gear.json
        import json
        for r in json.load(open(os.path.join(HERE, "data", "mp-snow-swap-gear.json"))):
            if not big_surface(r["garment"], r["type"]):
                continue
            out.append((fnv(r["material"]), DONOR_TYPES[r["type"]][2]))
    if os.environ.get("T2R_FACTION_LOOKS") == "1":
        import json
        for fn in (("mp-snow-crew.json",) if os.environ.get("T2R_WINTER_CREW") != "0" else ()) + ("mp-snow-gear.json",):      # natively snow-capable parts of the winter looks (crew bodies / heads, Jackson winter hoodies)
            for r in json.load(open(os.path.join(HERE, "data", fn))):
                out.append((fnv(r["material"]), r["param"]))
    return list(dict.fromkeys(out))      # one row per (material, layer): the same material in several paks (shared Jackson / kit materials) needs one row, not one per pak


def material_sids():
    return [s for s, _p in wanted()]


def _rows(d):
    """[(table symbol, row offset, param name, name offset)] of every g_snowStrength0N row of material-param.bin
    (rows: 0x48 bytes, +0 sid, +8 name ptr, +0x20 floats)"""
    out = []
    n = struct.unpack_from("<I", d.data, 0x14)[0]
    for i in range(n):
        o = 0x28 + i * 24
        try:
            ob = d.q(o + 16)
            cnt, arr = d.q(ob) & 0xffffffff, d.q(ob + 8)
            for k in range(cnt):
                r = arr + 0x48 * k
                sp = d.q(r + 8)
                nm = d.data[sp:d.data.index(b"\0", sp)].decode()
                if nm.startswith("g_snowStrength0") and d.is_ptr(r + 8):
                    out.append((d.q(o), r, nm, sp))
        except (ValueError, struct.error):
            continue
    return out


def _grown(game_bin, nwant):
    """DcFile of material-param.bin with at least nwant g_snowStrength rows: when the game's own 67 rows do not suffice, the array of the last snow table is rebuilt at the end of
    the data (old rows + copies of its first snow row, DcFile.append) and the table repointed at it - so more garments never abort the build (the ext drives tables by symbol; a
    longer table is still the same table)"""
    d = DcFile(open(game_bin, "rb").read())
    rows = _rows(d)
    extra = nwant - len(rows)
    if extra <= 0:
        return d
    tbl = rows[-1][0]
    n = struct.unpack_from("<I", d.data, 0x14)[0]
    ob = next(d.q(0x28 + i * 24 + 16) for i in range(n) if d.q(0x28 + i * 24) == tbl)
    cnt, arr = d.q(ob) & 0xffffffff, d.q(ob + 8)
    first = next(r for r in rows if r[0] == tbl)
    blob, slots = d.copy_block(arr, cnt * 0x48)
    tb, ts = d.copy_block(first[1], 0x48)
    for _ in range(extra):
        slots += [len(blob) + o for o in ts]
        blob += tb
    at = d.append(blob, ptr_slots=slots)
    ob_cnt_hi = d.q(ob) & ~0xffffffff
    d.set_q(ob, ob_cnt_hi | (cnt + extra))
    d.set_ptr(ob + 8, at)
    return d


def plan(game_bin, want=None):
    """([(row, sid, param)], table symbols that hold them): every wanted material gets a distinct g_snowStrength row (one already named like its
    param first: fewest edits); missing rows are appended to the last snow table (_grown)"""
    want = wanted() if want is None else want
    rows = _rows(_grown(game_bin, len(want)))
    free = sorted(rows, key=lambda r: (r[0], r[1]))
    out = []
    for sid, prm in want:
        k = next((i for i, r in enumerate(free) if r[2] == prm), 0)
        out.append((free.pop(k), sid, prm))
    return out, sorted({r[0] for r, _s, _p in out})


def make_overlay(game_bin, overlay_dc1, want=None):
    """material-param.bin whole-file overlay (rows of the SP snow tables pointed at the garments' materials; grown only when the game's rows do not suffice)"""
    want = wanted() if want is None else want
    d = _grown(game_bin, len(want))
    use, tables = _plan_rows(d, want)
    name_of = {}
    for r in _rows(d):
        name_of.setdefault(r[2], r[3])
    for (tbl, r, nm, sp), sid, prm in use:
        d.set_q(r, sid)                                   # (a plain sid, not a pointer slot)
        d.set_ptr(r + 8, name_of[prm])                    # param name -> the material's own layer string (a pointer slot already)
        for k in range(3):
            struct.pack_into("<f", d.data, r + 0x20 + 4 * k, 1.0)
    os.makedirs(overlay_dc1, exist_ok=True)
    open(os.path.join(overlay_dc1, "material-param.bin"), "wb").write(d.save())
    print(f"mp_snow: material-param.bin: {len(use)} rows in {len(tables)} tables -> {len(ALL)} garments + {len(use) - len(ALL)} crew materials")
    return tables


def _plan_rows(d, want):
    free = sorted(_rows(d), key=lambda r: (r[0], r[1]))
    out = []
    for sid, prm in want:
        k = next((i for i, r in enumerate(free) if r[2] == prm), 0)
        out.append((free.pop(k), sid, prm))
    return out, sorted({r[0] for r, _s, _p in out})


def write_header(game_bin=None):
    """tools/ext/mp_snow_built.h (generated, not committed): does THIS build carry the pak + tables (the ext drives them only then) and which tables"""
    tabs = []
    if ON:
        game_bin = game_bin or os.path.join(ROOT, "re", "gamebin", "dc1", "material-param.bin")
        tabs = plan(game_bin)[1]
    text = ("// generated by tools/features/mp_snow.py - do not edit, do not commit\n"
            f"#define T2R_MP_SNOW_BUILT {int(ON)}\n"
            f"#define MP_SNOW_WINTER_LOOKS {int(ON and os.environ.get('T2R_FACTION_LOOKS') == '1')}\n"
            f"#define MP_SNOW_NTABLES {len(tabs)}\n"
            "#define MP_SNOW_TABLES " + ("{" + ", ".join("0x%016xULL" % t for t in tabs) + "}" if tabs else "{0}") + "\n")
    old = open(HEADER, encoding="utf-8").read() if os.path.exists(HEADER) else None
    if old != text:
        open(HEADER, "w", encoding="utf-8", newline="\n").write(text)
