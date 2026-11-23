"""Character customization: the item table (re/customize-1117.md).

One table per (faction, sex). Each category is an ordered list of items. An item index is what the
client saves (t2r-customize.txt) and sends to the other players (MSG_CUSTOM_LOOK), so the lists are
APPEND-ONLY: never reorder or delete an entry, mark it hidden instead.

Every part name is a real look2 mesh of the game's dc1/look2/characters.bin, taken from the SP / MP
look records that wear it (SRC_LOOK). tools/tests/test_customize_items.py checks every part and pak.

Tiers (what it costs to make an item wearable in MP):
  1  the paks are already in the MP level today (FACTION_LOOK_ACTORS / FEMALE_LOOK_ACTORS): free.
  2  same skeleton family, the pak is SP-only: add the actor pak to the level (VRAM + winmm size) and
     build its armour pushed copy (tools/models/armour_push.py).
  3  other skeleton (brute x1.1, named characters, mod parts not built for this sex): needs a fit /
     retarget pass first (crew_retarget.py, armour_warp.py). Listed so the morning review sees them.

  python tools/features/customize_items.py            # prints the table + pak budget
  python tools/features/customize_items.py --header   # writes tools/ext/customize_items.h
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

FACTIONS = ("wlf", "scar")          # ext order: 0 = WLF, 1 = Seraphites (clan_t.fac 1 / 2 minus one)
SEXES = ("m", "f")
# The categories in SAVED order (the file's "look" numbers, the wire, CZ_* indexes): the wearables, then SEX (last: customize_core.h
# CZ_NWEAR = the ones before it). MASK (its own category, so both a hat and a gas mask can work
# together) was added at the end of the wearables, so an older file's six numbers keep their meaning and its mask is NONE.
CATS = ("hat", "torso", "lower", "backpack", "face", "melee", "mask", "sex")
# the tab bar's order (mockup: hat, torso, lower, backpack, fist/knife, sex; FACE added by the spec; MASK next to HEADWEAR)
TAB_ORDER = ("hat", "mask", "torso", "lower", "backpack", "face", "melee", "sex")
assert sorted(TAB_ORDER) == sorted(CATS) and CATS[-1] == "sex"
CAT_LABEL = {"hat": "HEADWEAR", "torso": "TORSO", "lower": "LOWER", "backpack": "BACKPACK", "face": "FACE",
             "melee": "MELEE STYLE", "mask": "MASK", "sex": "SEX"}
FAC_LABEL = {"wlf": "WLF", "scar": "SERAPHITES"}


def item(label, parts=(), props=(), paks=(), tier=1, src=None, hide=(), note=""):
    """parts / props: look2 meshes / cloth props worn; hide: parts present but hidden at spawn (hood up)."""
    return {"label": label, "parts": list(parts), "props": list(props), "paks": list(paks), "tier": tier,
            "src": src, "hide": list(hide), "note": note, "hid": 0}        # hid 1 = a row only its owner's page lists (KELLIE)


ARMS = ("-loarm-l", "-loarm-r", "-uparm-l", "-uparm-r")
LEGS = ("-loleg-l", "-loleg-r", "-upleg-l", "-upleg-r")

# paks loaded by the MP level today (dc_data_patches.FACTION_LOOK_ACTORS + FEMALE_LOOK_ACTORS + BACKPACK_RIG mod paks)
MP_PAKS_NOW = {
    "scar-male-head-13", "scar-male-head-01", "scar-male-head-12", "scar-male-head-06", "scar-male-head-09", "scar-male-head-07",
    "scar-male-hooddown", "scar-male-hoodup", "scar-male-hood-animprop", "scar-male-a-jacket-kit", "scar-male-a-jacket-cloth", "scar-male-b-jacket-kit",
    "scar-male-b-jacket-cloth", "scar-male-c-jacket-kit", "scar-male-c-jacket-cloth", "scar-male-a-legs-kit", "scar-male-b-legs-kit",
    "scar-male-c-legs-kit", "scar-t2r-bp-rigged",
    "militia-male-11-kit", "militia-male-08-kit", "militia-male-12-kit", "militia-male-05-kit", "militia-male-13-kit",
    "militia-male-14-kit", "militia-male-a-legs-kit", "militia-male-b-legs-kit", "militia-male-c-legs-kit", "militia-male-d-legs-kit",
    "militia-male-hat-08", "militia-male-hat-14", "militia-male-05-jacket-cloth", "militia-t2r-bp-rigged-11", "militia-t2r-bp-rigged-12",
    "militia-male-backpack-08", "militia-male-backpack-05", "militia-male-backpack-13", "militia-male-backpack-14",
    "militia-male-1hmelee-holster",
    "scar-female-head-11", "scar-female-head-09", "scar-female-hooddown", "scar-female-hoodup", "scar-female-hood-animprop", "scar-female-a-jacket-kit",
    "scar-female-a-jacket-cloth", "scar-female-a-legs-kit", "scar-female-b-legs-kit", "scar-female-backpack",
    "militia-female-13-kit", "militia-female-12-kit", "militia-female-a-legs-kit", "militia-female-d-legs-kit",
    "militia-female-hat-13", "militia-female-backpack-13", "militia-female-backpack-12", "militia-female-1hmelee-holster",
}


# The stock garments no MP level loaded (not all items previewed, only e.g. gasmasks and some specific jackets/pants): a
# row whose paks are not in the level cannot be shown or worn. These 54 are the game's own files in sp-common.psarc (mounted in MP: no mod
# size, 333 MB on disk), listed in the level by dc_data_patches like the look actors: every WLF kit, the Seraphite heads, the strap coats,
# the other caps / bags / legs. Not here (other archives, the rows stay tier 2): militia-female-07-kit, militia-male-mask-02,
# militia-female-mask-03. scar-male-head-02 is in sp-common but no look of the game wears it (no look2-mesh record in characters.bin:
# customize_looks would have nothing to copy), so FACE 02 of the Seraphite men stays tier 2. T2R_CZ_STOCK=0 = off.
STOCK_EXTRA = [
    "militia-female-01-kit", "militia-female-02-kit", "militia-female-03-kit", "militia-female-04-kit", "militia-female-05-kit",
    "militia-female-06-kit", "militia-female-08-kit", "militia-female-09-kit", "militia-female-10-kit", "militia-female-11-kit",
    "militia-female-14-kit", "militia-female-15-kit", "militia-female-b-legs-kit", "militia-female-backpack-04", "militia-female-backpack-10",
    "militia-female-c-legs-kit", "militia-female-hat-10", "militia-female-hat-15", "militia-male-01-kit", "militia-male-02-jacket-cloth",
    "militia-male-02-kit", "militia-male-03-kit", "militia-male-04-kit", "militia-male-06-kit", "militia-male-07-kit", "militia-male-09-kit",
    "militia-male-10-kit", "militia-male-15-kit", "militia-male-16-kit", "militia-male-17-kit", "militia-male-hat-04", "militia-male-hat-15-detach",
    "militia-male-hat-17", "scar-female-b-jacket-cloth", "scar-female-b-jacket-kit", "scar-female-head-02", "scar-female-head-03",
    "scar-female-head-04", "scar-female-head-05", "scar-female-head-06", "scar-female-head-07", "scar-female-head-08", "scar-female-head-10",
    "scar-female-knife-jacket-cloth", "scar-female-machete-jacket-cloth", "scar-female-pistol-jacket-cloth", "scar-male-head-03",
    "scar-male-head-04", "scar-male-head-05", "scar-male-head-08", "scar-male-head-10", "scar-male-head-11", "scar-male-machete-jacket-cloth",
    "scar-male-pistol-jacket-cloth",
]
STOCK_ON = os.environ.get("T2R_CZ_STOCK", "1") != "0"
if STOCK_ON:
    MP_PAKS_NOW |= set(STOCK_EXTRA)


def _tier(paks, base=2):
    return 1 if all(p in MP_PAKS_NOW for p in paks) else base


# WLF bags and trousers by what the card shows (named by what they look like: school bag,
# rucksack, backpack, military pack; same for pants)
WLF_BAG = {"m": {"11": "CANVAS DAYPACK", "12": "PATCHED RUCKSACK", "08": "FIELD PACK", "05": "TACTICAL PACK", "13": "SCHOOL BAG"},
           "f": {"13": "SCHOOL BAG", "04": "PATCHED RUCKSACK", "10": "TACTICAL PACK"}}
WLF_PANTS = {"m": {"PANTS A": "BROWN CARGO PANTS", "PANTS B": "OLIVE CARGO PANTS", "PANTS C": "FADED CARGO PANTS",
                   "PANTS D, DROP HOLSTER": "CARGO PANTS, DROP HOLSTER"},
             "f": {"PANTS A": "KHAKI CARGO PANTS", "PANTS B": "BELTED CARGO PANTS", "PANTS C": "FADED CARGO PANTS",
                   "PANTS D, DROP HOLSTER": "CARGO PANTS, DROP HOLSTER"}}
# WLF garment names (from the card renders; the kit numbers mean nothing to a player)
WLF_TORSO = {
    "m": {"01": "CREW SWEATER", "02": "FIELD JACKET", "03": "PATCH VEST", "04": "ROLLED-SLEEVE JACKET", "05": "OVERSHIRT",
          "06": "LEATHER JACKET", "07": "HENLEY, HARNESS", "08": "WORN ZIP JACKET", "09": "M-65 JACKET", "10": "LONG SLEEVE, HARNESS",
          "11": "HOODIE", "12": "BLACK LEATHER JACKET", "13": "THERMAL, HARNESS", "14": "HOODED JACKET, HARNESS", "15": "WORK JACKET",
          "16": "UTILITY JACKET", "17": "LIGHT JACKET"},
    "f": {"01": "FLEECE VEST", "02": "HALF-ZIP PULLOVER", "03": "FIELD JACKET", "04": "OPEN JACKET", "05": "QUILTED VEST, HARNESS",
          "06": "JACKET AND HOODIE", "07": "SHELL JACKET, HARNESS", "08": "PUFFER VEST", "09": "SOFTSHELL JACKET", "10": "CANVAS JACKET",
          "11": "UTILITY VEST", "12": "DARK JACKET, HARNESS", "13": "QUILTED VEST", "14": "ZIP JACKET, HARNESS", "15": "LIGHT JACKET"},
}
# HANDS THAT FOLLOW THE FACE (many tops still dictate the hand skin colour): a WLF top's hands are submeshes of its kit
# with the SP soldier's own arm material - one tone under every face, and no tint mask. tools/models/wlf_hand_tint.py makes a copy of
# each top's kit with that skin on the Seraphite kit hands' tinting material; the TORSO row wears the copy's torso + arm parts
# (their look2 records: copies of the stock ones + a tint key, customize_looks.py), and every outfit record has a palette per
# face in the face's skin colour (tools/models/wlf_face_tint.py -> data/wlf_face_tint.json; customize_looks.patch_customize_tints).
# data/wlf_hand_tint.json + the prebuilt paks in HANDTINT_DIR; no file / T2R_CZ_HANDTINT=0 = the stock kits, as before.
HANDTINT_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "data", "wlf_hand_tint.json")
HANDTINT_COLOURS = os.path.join(os.path.dirname(HANDTINT_LIST), "wlf_face_tint.json")
HANDTINT_DIR = os.environ.get("T2R_CZ_HANDTINT_DIR", "../t2r-wt/cz-handtint1")


def _handtint():
    # OFF unless T2R_CZ_HANDTINT=1 (build #19): the 32 kit copies are 804 of the engine's 5000 geometry slots (24 per kit
    # copy, drawn or not - tools/features/geo_count.py) and took the MP level from 3826 to 4630; with a map's or the menu scene's
    # geometries beside it the table ran over and the game crashed (ResourceTable::LoginGeometry). The tint returns inside the
    # stock kits (0 slots); until then the copies stay out of the build.
    if os.environ.get("T2R_CZ_HANDTINT", "0") != "1" or not os.path.exists(HANDTINT_LIST) or not os.path.exists(HANDTINT_COLOURS):
        return None
    import json
    k = json.load(open(HANDTINT_LIST))
    for a, (size, _sha) in k["paks"].items():
        f = os.path.join(HANDTINT_DIR, a + ".pak")
        if not os.path.exists(f) or os.path.getsize(f) != size:
            return None
    k["colours"] = json.load(open(HANDTINT_COLOURS))
    return k


HANDTINT = _handtint()
HANDTINT_TOPS = {(t["sex"], t["kit"]): t for t in (HANDTINT["tops"] if HANDTINT else ())}
# THE TINT INSIDE THE STOCK KITS (after build #19): the same tinting arm material, but put into the kit pak itself
# (tools/models/wlf_hand_tint.tint; build_dll.stage_tint_kits replaces actor97/militia-<sex>-NN-kit.pak under its own name, on top
# of the snow build's version where there is one): no copy, so no new actor and none of the engine's 5000 geometry slots. The
# TORSO rows keep the stock parts. Every look that wears those parts needs a tint key on them + a palette, or its hands are
# white: the CUSTOMIZE records (customize_looks.patch_customize_looks / _tints, per skin tone group) and the WLF pool looks with
# their twins (customize_looks.patch_pool_hand_tints: a palette in the look's own head's colour). T2R_CZ_TINT_KITS=0 = stock kits.
TINT_KITS = {}
TINT_COLOURS = {}
if not HANDTINT and os.environ.get("T2R_CZ_TINT_KITS", "1") != "0" and os.path.exists(HANDTINT_COLOURS):
    import json as _json
    TINT_COLOURS = _json.load(open(HANDTINT_COLOURS))
    TINT_KITS = {s: sorted(TINT_COLOURS[s]) for s in ("m", "f")}        # every WLF kit with a head colour: 17 male, 15 female
    HANDTINT = {"colours": TINT_COLOURS, "tops": [], "paks": {}, "kits": True}       # (wlf_tones / the header's tone table read it)


def tint_kit_pak(sex, kit):
    return "militia-%s-%s-kit" % ("male" if sex == "m" else "female", kit)


# the kit parts whose look2-mesh records get the tint key: torso + the four arm parts of every tint kit
TINT_PARTS = {"%s-%s-torso%s" % ("militia-male" if s == "m" else "militia-female", k, a): (s, k)
              for s, ks in TINT_KITS.items() for k in ks for a in ("", "-loarm-l", "-loarm-r", "-uparm-l", "-uparm-r")}
HANDTINT_PARTS = {c: (t["pak"], s) for t in HANDTINT_TOPS.values() for s, c in t["parts"].items()}      # copy part -> (pak, stock part)
# (face 08 removed: the male head 08 has hair only below a cap's line, a bare scalp above)
DROP_FACES = {"m": ("08",), "f": ()}
HAT_HEADS = {"m": ("01", "07", "09", "10", "11", "13"),   # head_grp submeshes: 01 hat, 07 / 10 / 13 beanie, 09 baseball_cap, 11 bandana
             "f": ("08", "11", "12")}                     # beanie2 / beanie
WLF_CAP = {"m": {"04": "WLF CAP", "08": "PATROL CAP", "14": "FIELD CAP", "15": "BALL CAP", "17": "PATCH CAP"},
           "f": {"10": "PATROL CAP", "13": "BALL CAP", "15": "FADED CAP"}}


def _masks(sex, fac):
    """MASK (its own category, so both a hat and a gas mask can work
    together)"; then "seraphites should also be allowed to wear gasmasks and the mask section should also feature half masks too"):
    both factions' lists carry every mask - NONE, then the faction's own kind first. A mask is a head part of the shared base rig:
    the gas masks were fitted to the militia heads, the half masks (the winter build's kerchiefs, without the hood they came with:
    the hood is the HEADWEAR row's) to the Seraphite pool heads; on the other faction's heads the fit is as it falls."""
    p = "militia-" + ("male" if sex == "m" else "female")
    m = "02" if sex == "m" else "03"
    # (repeating options are skipped (backpacks, gasmasks, etc): the militia masks 02 / 03 / 05 / 09
    # (male) and 03 / 08 / 11 (female) are ONE mask on the card (rms 0.035 - 0.042, re/customize-1117.md "Repeats"): one row each)
    def gm(label, part, src, t3=None):
        # (UNDER A HAT, MASK_UNDER: the row also wears the mask's under-hat shape(s); the HEADWEAR rows' hide lists leave one drawn)
        un = {c: mask_under_part(part, sex, c) for c in MASK_UNDER}
        paks = [part] + list(un.values())
        it = item(label, paks, paks=paks, src=src, tier=_tier(paks) if t3 is None else _tier(paks, t3))
        it["under"] = un
        return it
    gas = [gm("GAS MASK", p + "-mask-" + m, "%s-%s-gasmask" % (p, m))]
    # the story gas masks (varied gas masks: Dina, Ellie, Abby, Lev, Eugene's): mod-built parts (MOD_PARTS)
    for key, label in GASMASKS:
        gas.append(gm(label, gasmask_actor(key, sex), "story gas mask (tools/models/wlf_gasmasks.py)", 3))
    if HALFMASK:            # one cloth per face (the FACE rows wear it, table() below): no parts of its own
        hp = sorted({a for k, (a, _p) in HALFMASK["parts"].items() if a.startswith("scar-t2r-hf" + sex)})
        it = item(HALFMASK_LABEL, [], paks=hp, tier=_tier(hp), note="mod part, one per face (halfmask_cloth.py)")
        it["halfmask"] = 1
        half = [it]
    else:
        half = [item(lb, [part], paks=[kit], tier=_tier([kit]), note="mod part (winter build)" + nt) for lb, part, kit, nt in HALF_MASKS[sex]]
    return [item("NONE", tier=1)] + (gas + half if fac == "wlf" else half + gas)


def _wlf(sex):
    s = "male" if sex == "m" else "female"
    p = "militia-" + s
    n_kits = 17 if sex == "m" else 15
    kits = ["%02d" % k for k in range(1, n_kits + 1) if not (sex == "f" and k == 7 and False)]
    T = {c: [] for c in CATS}
    # HEADWEAR: none, hats, gas masks (SP looks militia-*-NN / -NN-gasmask)
    T["hat"].append(item("NONE", tier=1))
    hats = ("04", "08", "14", "15", "17") if sex == "m" else ("10", "13", "15")
    for h in hats:
        hp = p + "-hat-" + h + ("-detach" if (sex, h) == ("m", "15") else "")    # hat-15 ships only as the -detach pak
        T["hat"].append(item(WLF_CAP[sex][h], [p + "-hat-" + h], paks=[hp], src="%s-%s" % (p, h), tier=_tier([hp])))
    # (repeating options are skipped (backpacks, gasmasks, etc): the militia masks 02 / 03 / 05 / 09
    # (male) and 03 / 08 / 11 (female) are ONE mask on the card (rms 0.035 - 0.042, re/customize-1117.md "Repeats"): one row each)
    T["mask"] = _masks(sex, "wlf")
    # TORSO: every WLF shirt / jacket (kit torso + split arms, + the jacket cloth prop where the look has one)
    cloth = {"m": {"02": "militia-male-02-jacket-cloth", "05": "militia-male-05-jacket-cloth"}, "f": {}}[sex]
    for k in kits:
        tor = "%s-%s-torso" % (p, k)
        paks = ["%s-%s-kit" % (p, k)] + ([cloth[k]] if k in cloth else [])
        parts = [tor] + [tor + a for a in ARMS]
        ht = HANDTINT_TOPS.get((sex, k))               # (the top's copy whose bare skin follows the face: HANDTINT)
        if ht:
            parts = [ht["parts"][x] for x in parts]
            paks = [ht["pak"]] + paks[1:]
        T["torso"].append(item(WLF_TORSO[sex][k], parts, [cloth[k]] if k in cloth else [], paks,
                               src="%s-%s" % (p, k) + (" (hand-tint copy, wlf_hand_tint.py)" if ht else ""), tier=_tier(paks)))
    # LOWER: legs kit + the holster the SP looks wear with it (sidearm-stow rule: belts / holsters stay on the pants)
    # (many clothing options repeat: the kit holsters 05 / 07 / 10 / 13 / 14 are one model (default_holster,
    # material holster-01), so "PANTS B, THIGH HOLSTER" / "HIP HOLSTER" / "PANTS B" read as the same item: one row per legs kit)
    lows = [("a", None, "PANTS A"), ("b", None, "PANTS B"), ("c", None, "PANTS C"), ("d", "d-holster", "PANTS D, DROP HOLSTER")]
    for legs, hol, label in lows:
        lp = "%s-%s-legs" % (p, legs)
        parts = [lp] + [lp + x for x in LEGS] + [p + "-1hmelee-holster"]
        paks = ["%s-%s-legs-kit" % (p, legs), p + "-1hmelee-holster"]
        if hol:
            parts.append(p + "-" + hol)
            m = re.match(r"holster-(\d+)", hol)
            paks.append("%s-%s-kit" % (p, m.group(1)) if m else "%s-d-legs-kit" % p)
        hip = not hol
        if hip:
            # (some pants (olive cargo/faded cargo) came with chest holsters, all come with hip holsters instead
            # (a later version may switch to custom front holster anims): every trousers row wears the drop
            # holster of the d-legs kit (holster_d: right hip / thigh, y 0.6 .. 1.07); the chest harness a pool look carries is no
            # longer taken over as an extra - customize_core.h cz_select)
            parts.append(p + "-d-holster")
            paks.append("%s-d-legs-kit" % p)
        it = item(WLF_PANTS[sex][label], parts, paks=paks, tier=_tier(paks))
        it["hip"] = hip
        T["lower"].append(it)
    # BACKPACK: every WLF bag (a bag is required: the MP backpack / crafting rule); rigged copies where built
    # (repeating ones skipped: male 03 = 13, 07 = 12, 14 = 11 (the tan day pack again); female 12 / 06 / 14 / 15 = 13 (the grey
    # day pack, rms 0.03 - 0.06). One row per bag that reads differently on the card.)
    bags = ("11", "12", "08", "05", "13") if sex == "m" else ("13", "04", "10")
    rig = {"11": "militia-t2r-bp-rigged-11", "12": "militia-t2r-bp-rigged-12"} if sex == "m" else {}
    for b in bags:
        part = rig.get(b, "%s-backpack-%s" % (p, b))
        T["backpack"].append(item(WLF_BAG[sex][b], [part], paks=[part], src="%s-%s-backpack" % (p, b), tier=_tier([part])))
    # FACE: every WLF head (inside the look's kit pak: a face costs the whole kit, 7-10 MB) but the ones with headwear modelled into
    # the head mesh (some faces already have hats on them): a beanie / cap / bandana submesh in head_grp, so it cannot be
    # left off and would stack under a HEADWEAR item. A hatless copy of these heads = a mod-built head (later).
    for k in kits:
        if k in HAT_HEADS[sex] or k in DROP_FACES[sex]:
            continue
        _hf = HEAD_FIX.get((sex, k))
        _hp, _hk = (_hf["part"], _hf["pak"]) if _hf else ("%s-head-%s" % (p, k), "%s-%s-kit" % (p, k))
        _hh = (_hf or {}).get("hair")                  # (a head without top hair wears another list face's hair as a second part)
        _fparts, _fpaks = [_hp] + ([_hh["part"]] if _hh else []), [_hk] + ([_hh["pak"]] if _hh else [])
        T["face"].append(item("FACE %s" % k, _fparts, paks=_fpaks, src="%s-%s" % (p, k) + (" (bare-head copy, head_fix.py)" if _hf else "") +
                              (" + the hair of FACE %s" % _hh["donor"] if _hh else ""), tier=_tier(_fpaks)))
    return T


# Mod-built parts: own actor paks the data build makes (tools/models/scar_garment_port.py: whole Seraphite shirts on the base skeleton,
# tools/models/wlf_gasmasks.py: the story gas masks on the MP head). No look2 record wears them, so customize_looks gives each a copy of
# its template part's look2-mesh record (region / gore group kept) with its own name. part -> (actor, template part)
MOD_PARTS = {}
# the story gas masks (tools/models/wlf_gasmasks.py MASKS, same order + labels; dc_data_patches.GASMASK_ACTORS): the look2 record of each is a copy of
# the sex's stock militia mask record. T2R_GASMASKS=0 (no paks in the level): tier 3 = not in multiplayer yet.
GASMASKS = (("dina", "DINA'S GAS MASK"), ("ellie", "ELLIE'S GAS MASK"), ("abby", "ABBY'S GAS MASK"), ("lev", "LEV'S GAS MASK"), ("bong", "BONG MASK"))
GASMASK_TEMPLATE = {"m": "militia-male-mask-02", "f": "militia-female-mask-03"}
# the half masks (dc_data_patches.WINTER_MASK_PARTS / WINTER_FSCAR_MASK: the Seraphite winter looks' kerchiefs, in the level with
# T2R_MP_SNOW=1 - the release builds): label, part, kit pak, note. Their look2 records are made for the winter looks AFTER the
# CUSTOMIZE looks are built, so here they are mod parts too: a copy of the sex's stock mask record (a head-region part).
HALF_MASKS = {"m": (("HALF MASK I", "scar-t2r-mask01-torso", "scar-t2r-mask01-kit", ", heads 13/01/12/09"),
                    ("HALF MASK II", "scar-t2r-mask02-torso", "scar-t2r-mask02-kit", ", heads 06/07")),
              "f": (("HALF MASK", "scar-t2r-mask03-torso", "scar-t2r-mask03-kit", ""),)}


def gasmask_actor(key, sex):
    return "t2r-gm-%s-%s" % (sex, "bong-a" if key == "bong" else key)


# UNDER A HAT (relayed by the dev-model session: "actually gas masks should adapt, sticking out straps should hide and
# thatll be enough"): every gas mask has a second shape without the harness triangles a hat covers (tools/models/wlf_gasmasks.py
# "UNDER A HAT": a renamed copy of the mask's pak; which triangles: tools/models/mask_under.py -> data/mask_under.npz + .json).
# MASK_UNDER = the shapes' class letters: ("u",) one shape under every crown-covering hat, ("b", "s") big hats (beanies, hood up) /
# small hats (caps, brimmed hats); () = no data file: the full mask under every hat. A mask row wears the full part and the
# shapes; table() gives every HEADWEAR row the hide list that leaves exactly one of them drawn.
def _mask_under():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "data", "mask_under.json")
    # (it looked better with the slight clips: the cut table also took face-piece triangles; the
    #  under-hat shapes are OFF by default, the full mask is drawn under every hat. T2R_CZ_MASK_UNDER=1 turns them back on.)
    if os.environ.get("T2R_CZ_MASK_UNDER", "0") == "0" or os.environ.get("T2R_GASMASKS", "1") == "0" or not os.path.exists(f):
        return ()
    import json
    j = json.load(open(f))
    assert sorted(j["sexes"]) == ["f", "m"], "mask_under.json: made for %s only (tools/models/mask_under.py)" % j["sexes"]
    return tuple(j["classes"])


MASK_UNDER = _mask_under()


def mask_under_part(part, sex, cls):
    """= wlf_gasmasks.under_actor: the class prefix over the full part's first 9 characters (same length)"""
    pre = "t2r-g%s-%s-" % (cls, sex)
    return pre + part[len(pre):]


for _s in SEXES:
    for _k, _l in GASMASKS:
        MOD_PARTS[gasmask_actor(_k, _s)] = (gasmask_actor(_k, _s), GASMASK_TEMPLATE[_s])
    for _c in MASK_UNDER:
        for _full in [GASMASK_TEMPLATE[_s]] + [gasmask_actor(_k, _s) for _k, _l in GASMASKS]:
            MOD_PARTS[mask_under_part(_full, _s, _c)] = (mask_under_part(_full, _s, _c), GASMASK_TEMPLATE[_s])
            MP_PAKS_NOW.add(mask_under_part(_full, _s, _c))
for _s in SEXES:
    for _lb, _part, _kit, _nt in HALF_MASKS[_s]:
        MOD_PARTS[_part] = (_kit, GASMASK_TEMPLATE[_s])
# PER-FACE HALF MASK (on the winter build's kerchiefs: "bad fit on most faces", then the reference bandana: "should fit
# like this" ... "Roll out"): one bandana per face, built on that face's own head (devmodel/face/hatfit/halfmask_cloth.py: the cloth
# sheet over the nose, down the throat to a tip, round the neck to the knot), 5 faces a pak (copies of a mask kit, NEW actors
# scar-t2r-hf<sex>-NN-kit). The list file + paks: T2R_CZ_HALFMASK_DIR/halfmask_faces.json = {"paks": {pak: [bytes, sha1]},
# "parts": {face key: [pak, part]}, "rows": {"<fac>-<sex>": {FACE label: [pak, part]}}}. ON when the dir holds the json; else the
# winter build's HALF MASK rows (HALF_MASKS) as before. With it: ONE row "HALF MASK" per list (the old I / II were one cloth on two
# head shapes); each FACE row wears its own cloth part, the HALF MASK row hides none of them, every other mask row hides them all.
HALFMASK_DIR = os.environ.get("T2R_CZ_HALFMASK_DIR", "")
HALFMASK_LABEL = "HALF MASK"
HALFMASK_CARD = {"m": "wm14", "f": "wf04"}       # the HALF MASK card: the cloth on this face (the WLF male default face; a plain female face)
HALFMASK_SLOTS = {"torso": "kerchief", "torso-loarm-l": "loarm_l", "torso-loarm-r": "loarm_r", "head": "|head_grp|", "holster": "|holster_grp|"}


def _halfmask():
    f = os.path.join(HALFMASK_DIR, "halfmask_faces.json") if HALFMASK_DIR else ""
    if not f or not os.path.exists(f):
        return None
    import json
    j = json.load(open(f))
    for a, (n, _sha) in j["paks"].items():
        p = os.path.join(HALFMASK_DIR, a + ".pak")
        assert os.path.exists(p) and os.path.getsize(p) == n, "halfmask_faces.json: %s missing or another size in %s" % (a, HALFMASK_DIR)
    return j


def halfmask_slot(key):
    """the card-render filter (submesh name substring) of a face's cloth part: the kit geometry it was written on (json "geo")"""
    return HALFMASK_SLOTS[HALFMASK["geo"][key]]


HALFMASK = _halfmask()
if HALFMASK:
    for _k, (_a, _p) in HALFMASK["parts"].items():
        MOD_PARTS[_p] = (_a, GASMASK_TEMPLATE["f" if _a.startswith("scar-t2r-hff") else "m"])
        MP_PAKS_NOW.add(_a)
if os.environ.get("T2R_MP_SNOW", "1") != "0":
    MP_PAKS_NOW |= {_kit for _s in SEXES for _lb, _part, _kit, _nt in HALF_MASKS[_s]}
if os.environ.get("T2R_GASMASKS", "1") != "0":
    MP_PAKS_NOW |= {gasmask_actor(_k, _s) for _s in SEXES for _k, _l in GASMASKS}


# Seraphite torso rows on the models rebuilt for the base bodies (the clothing models fixed so they make sense and have no
# cuts, spliced and reused where needed; tools/models/scar_garment_port.py, report in re/customize-1117.md). The SP rows named paks on other
# skeletons (crowd rig, brute x 1.1, the elders' own) or a coat kit without its coat (a torso stub). Each rebuilt item = its garment pak(s)
# + its bare skin on the face-tinted hand material (tools/models/skin_tint.py: scar-t2r-skn-<id>-kit, or the kit hands scar-t2r-hand<m|f>).
def _skn(t):
    return ["scar-t2r-skn-%s-torso%s" % (t, a) for a in ("",) + ARMS]


_HANDM = ["scar-t2r-handm-kit-torso%s" % a for a in ("",) + ARMS]
_HANDF = ["scar-t2r-handf-kit01-torso%s" % a for a in ("",) + ARMS]
_BRUTEF = ["scar-t2r-brutefem-01-torso"] + ["scar-t2r-brutefem-01-torso" + a for a in ("-uparm-l", "-uparm-r", "-loarm-l", "-loarm-r")] + \
    ["scar-t2r-brutefem-01-jacket-nocloth"]
PORTED = {
    ("m", "SHIRT I"): dict(parts=["scar-t2r-shirt1m-civilian-torso02"] + _skn("shr1m"), paks=["scar-t2r-shirt1m-civilian-torso02", "scar-t2r-skn-shr1m-kit"]),
    ("m", "SHIRT II"): dict(parts=["scar-t2r-shirt2m-civilian-torso01"] + _skn("shr2m"), paks=["scar-t2r-shirt2m-civilian-torso01", "scar-t2r-skn-shr2m-kit"]),
    ("m", "PRISONER SHIRT I"): dict(parts=["scar-t2r-shirt1m-prisoner-torso01"] + _skn("pri1m"),
                                    paks=["scar-t2r-shirt1m-prisoner-torso01", "scar-t2r-skn-pri1m-kit"]),
    ("m", "PRISONER SHIRT II"): dict(parts=["scar-t2r-shirt2m-prisoner-torso02"] + _skn("pri2m"),
                                     paks=["scar-t2r-shirt2m-prisoner-torso02", "scar-t2r-skn-pri2m-kit"]),
    ("m", "TORTURED"): dict(parts=_skn("tortm"), paks=["scar-t2r-skn-tortm-kit"]),
    ("m", "BRUTE JACKET"): dict(parts=["scar-t2r-brutem-shirt-civ01-crowd", "scar-t2r-brutem-01-torso"] + _skn("brutm"),
                                paks=["scar-t2r-brutem-shirt-civ01-crowd", "scar-t2r-brutem-01-torso", "scar-t2r-skn-brutm-kit"]),
    ("m", "ELDER (COLIN)"): dict(parts=["scar-t2r-elder1"] + _HANDM, paks=["scar-t2r-elder1", "scar-t2r-handm-kit-kit"]),
    ("m", "ELDER (REUBEN)"): dict(parts=["scar-t2r-elder2m"] + _skn("reubm"), props=["scar-t2r-elder2m-jkcloth"],
                                  paks=["scar-t2r-elder2m", "scar-t2r-elder2m-jkcloth", "scar-t2r-skn-reubm-kit"]),
    ("m", "ISLANDER (CHRIS)"): dict(parts=["scar-t2r-isle1m"] + _HANDM, paks=["scar-t2r-isle1m", "scar-t2r-handm-kit-kit"]),
    ("f", "SHIRT I"): dict(parts=["scar-t2r-shirt1f-civilianf-torso-02"] + _HANDF, paks=["scar-t2r-shirt1f-civilianf-torso-02", "scar-t2r-handf-kit01-kit"]),
    ("f", "SHIRT II"): dict(parts=["scar-t2r-shirt2f-civilian-torso01"] + _HANDF, paks=["scar-t2r-shirt2f-civilian-torso01", "scar-t2r-handf-kit01-kit"]),
    ("f", "COAT, PISTOL CUT"): dict(parts=["scar-t2r-shirt1f-civilianf-torso-02"] + _HANDF, props=["scar-female-pistol-jacket-cloth"],
                                    paks=["scar-t2r-shirt1f-civilianf-torso-02", "scar-t2r-handf-kit01-kit", "scar-female-pistol-jacket-cloth"]),
    ("f", "COAT, MACHETE CUT"): dict(parts=["scar-t2r-shirt1f-civilianf-torso-02"] + _HANDF, props=["scar-female-machete-jacket-cloth"],
                                     paks=["scar-t2r-shirt1f-civilianf-torso-02", "scar-t2r-handf-kit01-kit", "scar-female-machete-jacket-cloth"]),
    ("f", "PRISONER SHIRT I"): dict(parts=["scar-t2r-shirt1f-prisonerf-torso-01"] + _skn("pris1fx"),
                                    paks=["scar-t2r-shirt1f-prisonerf-torso-01", "scar-t2r-skn-pris1fx-kit"]),
    ("f", "PRISONER SHIRT II"): dict(parts=["scar-t2r-shirt2f-prisonerf-torso-02"] + _skn("pris2fx"),
                                     paks=["scar-t2r-shirt2f-prisonerf-torso-02", "scar-t2r-skn-pris2fx-kit"]),
    ("f", "BRUTE JACKET"): dict(parts=_BRUTEF, paks=_BRUTEF),
    ("f", "ISLANDER (EMILY)"): dict(parts=["scar-t2r-isle1f"] + _skn("emilyfx"), props=["scar-t2r-isle1f-jkcloth"],
                                    paks=["scar-t2r-isle1f", "scar-t2r-isle1f-jkcloth", "scar-t2r-skn-emilyfx-kit"]),
}
# Stock paks of WORLD archives that rows of the WLF lists wear (the gas mask did not preview): the plain gas mask of each sex
# and the 07 kit of the female WLF (SHELL JACKET, HARNESS + FACE 07). MP mounts sp-common / common only, so they ship like the rebuilt
# garments: scar_ports_pack.py takes each out of its archive, injects the textures no mounted dictionary holds (512 px) and lists it.
WORLD_STOCK = {"militia-male-mask-02": "world-find-nora.psarc", "militia-female-mask-03": "world-find-nora.psarc",
               "militia-female-07-kit": "world-seattle-arrival.psarc"}
PORTED_PAKS = sorted({x for v in PORTED.values() for x in v["paks"] if x.startswith("scar-t2r-")} | set(WORLD_STOCK))    # what the data build has to ship
# Shipping them: tools/models/scar_ports_pack.py writes the final files (missing textures injected at 512 px,
# trailer compacted) to PORTS_DIR and their sizes + sha1 to PORTS_LIST; build_dll.stage_scar_ports copies exactly those into actor97, the
# level lists them (dc_data_patches) and every rebuilt part / cloth prop gets a look2 record copied from a template (customize_looks:
# MOD_PARTS / MOD_PROPS). 34 paks, 194 MB, 93 MB packed. ON when the list and every listed file are there; T2R_CZ_PORTS=0 = off.
PORTS_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "data", "scar_ports.json")
# (cz-ports2: skin paks without the texture hash collision, + WORLD_STOCK. cz-ports stays as the builds before it list it.)
# (cz-ports4: ISLANDER LONG COAT's shirt cuffs on the wrists - scar_garment_port SLEEVE HELPERS; only scar-t2r-isle1f differs from cz-ports3.)
PORTS_DIR = os.environ.get("T2R_CZ_PORTS_DIR", "../t2r-wt/cz-ports4")
# the look2-prop record a rebuilt cloth prop copies: its source prop's own (the same cloth, renamed)
PORT_CLOTH_SRC = {"scar-t2r-elder2m-jkcloth": "scar-reuben-jacket-cloth", "scar-t2r-isle1f-jkcloth": "scar-emily-jacket-cloth"}
MOD_PROPS = {}                   # prop -> (actor, template prop), as MOD_PARTS


def _ports_on():
    if os.environ.get("T2R_CZ_PORTS", "1") == "0" or not os.path.exists(PORTS_LIST):
        return False
    import json
    lst = json.load(open(PORTS_LIST))
    if set(lst) != set(PORTED_PAKS):
        return False
    return all(os.path.exists(os.path.join(PORTS_DIR, a + ".pak")) and os.path.getsize(os.path.join(PORTS_DIR, a + ".pak")) == lst[a][0] for a in lst)


PORTS_ON = _ports_on()
# the SP coat cuts (pistol / machete / knife strap): cloth paks of sp-common that no look2-prop record names. With the stock paks in the
# level (STOCK_EXTRA) each gets a record copied from the same sex's default coat cloth (the same coat, another cut).
if STOCK_ON:
    for _s, _cuts in (("male", ("pistol", "machete")), ("female", ("pistol", "machete", "knife"))):
        for _c in _cuts:
            MOD_PROPS["scar-%s-%s-jacket-cloth" % (_s, _c)] = ("scar-%s-%s-jacket-cloth" % (_s, _c), "scar-%s-a-jacket-cloth" % _s)
if PORTS_ON:
    MP_PAKS_NOW |= set(PORTED_PAKS)
    for (_sx, _lb), _po in PORTED.items():
        _s = "male" if _sx == "m" else "female"
        for _part in _po["parts"]:
            if _part.startswith("scar-t2r-"):
                _pak = next(p for p in _po["paks"] if _part == p or (p.endswith("-kit") and _part.startswith(p[:-4])))
                _arm = next((a for a in ARMS if _part.endswith(a)), "")
                # the record a rebuilt part copies: the default coat kit's torso / that arm (region, gore group, attach)
                MOD_PARTS[_part] = (_pak, "scar-%s-a-jacket-torso%s" % (_s, _arm))
        for _pr in _po.get("props", ()):
            if _pr.startswith("scar-t2r-"):
                MOD_PROPS[_pr] = (_pr, PORT_CLOTH_SRC[_pr])
# cards that show the skin pak too (the item IS skin, or its open front shows the chest); the other torso cards show the garment alone
PORTED_SKIN_CARDS = ("scar-t2r-skn-tortm-kit", "scar-t2r-skn-pri2m-kit", "scar-t2r-skn-pris2fx-kit")


# Seraphite garment names (the WLF tops are named by garment (open jacket, quilted vest, harness etc), the Seraphite ones were just SHIRT 1
# SHIRT 2 etc): what the card shows, as the WLF names. Keys = the working labels of _scar (PORTED and the comments use those).
SCAR_NAMES = {
    "m": {"COAT I": "TAN RAINCOAT", "COAT II": "WEATHERED RAINCOAT", "SHIRT I": "LINEN SHIRT", "SHIRT II": "ROLLED-SLEEVE SHIRT",
          "COAT, PISTOL CUT": "RAINCOAT, HOLSTER STRAP", "COAT, MACHETE CUT": "RAINCOAT, MACHETE SLING",
          "PRISONER SHIRT I": "RAGGED SHIRT", "PRISONER SHIRT II": "OPEN RAGGED SHIRT", "BRUTE JACKET": "SHIRT, KNIFE HARNESS",
          "TORTURED": "TORTURED", "ELDER (COLIN)": "ELDER'S TUNIC", "ELDER (REUBEN)": "ELDER'S HOODED COAT",
          "ISLANDER (CHRIS)": "ISLANDER SHIRT",
          "TROUSERS A": "LINEN TROUSERS", "TROUSERS B": "FIELD TROUSERS", "TROUSERS C": "WORK TROUSERS", "PRISONER TROUSERS": "RAGGED TROUSERS",
          "SATCHEL": "LEATHER RUCKSACK"},
    "f": {"COAT I": "LEATHER RAINCOAT", "COAT II": "WORN LEATHER RAINCOAT", "SHIRT I": "STAINED SHIRT", "SHIRT II": "LINEN SHIRT",
          "COAT, PISTOL CUT": "SHIRT, HOLSTER STRAP", "COAT, MACHETE CUT": "SHIRT, MACHETE SLING", "COAT, KNIFE CUT": "RAINCOAT, KNIFE STRAP",
          "PRISONER SHIRT I": "OPEN RAGGED SHIRT", "PRISONER SHIRT II": "TORN SLEEVELESS TOP", "BRUTE JACKET": "HOODED RAINCOAT",
          "ISLANDER (EMILY)": "ISLANDER LONG COAT",
          "TROUSERS A": "WOOL TROUSERS", "TROUSERS B": "FIELD TROUSERS", "PRISONER TROUSERS": "RAGGED TROUSERS",
          "SATCHEL": "LEATHER RUCKSACK"},
}


def _scar_names(T, sex):
    for cat in ("torso", "lower", "backpack"):
        for it in T[cat]:
            it["label"] = SCAR_NAMES[sex].get(it["label"], it["label"])
        assert len({it["label"] for it in T[cat]}) == len(T[cat]), (sex, cat, [it["label"] for it in T[cat]])


def _ported(T, sex):
    p = "scar-male" if sex == "m" else "scar-female"
    for it in T["torso"]:
        po = PORTED.get((sex, it["label"]))
        if po:
            # (the hood stays although not all top options have one: a rebuilt top is no hooded coat kit - the kit's hood
            # parts, worn by the HEADWEAR row, are taken as their hidden-at-spawn records, customize_core.h cz_select)
            it.update(parts=list(po["parts"]), props=list(po.get("props", ())), paks=list(po["paks"]), tier=_tier(po["paks"]),
                      hide=[p + "-hooddown", p + "-hoodup"],
                      note="rebuilt for the base body (scar_garment_port.py); not in the MP data until the build ships PORTED_PAKS")


def _scar(sex):
    s = "male" if sex == "m" else "female"
    p = "scar-" + s
    T = {c: [] for c in CATS}
    hood = [p + "-hooddown", p + "-hoodup"]
    hpaks = [p + "-hooddown", p + "-hoodup", p + "-hood-animprop"]
    T["hat"].append(item("HOOD DOWN", hood, hide=[p + "-hoodup"], paks=hpaks, tier=_tier(hpaks[:2])))
    T["hat"].append(item("HOOD UP", hood, hide=[p + "-hooddown"], paks=hpaks, tier=_tier(hpaks[:2])))
    T["mask"] = _masks(sex, "scar")
    # TORSO: all the Seraphite coats, the shirt alone, and other clothing Seraphites wear in the game.
    # A coat = kit torso (sleeveless shirt + sleeves) + its cloth prop (the coat body). Without the prop = the shirt.
    # (many clothing options repeat: the cards of COAT III / SHIRT III, the plain / hatchet / heavy cuts and the
    # female long / short coats match another row (rms < 0.04 on the card, re/customize-1117.md "Repeats"): only the rows that read
    # as their own garment stay)
    for j, nm in (("a", "I"), ("b", "II")):
        tor = "%s-%s-jacket-torso" % (p, j)
        kit = "%s-%s-jacket-kit" % (p, j)
        cl = "%s-%s-jacket-cloth" % (p, j)
        T["torso"].append(item("COAT %s" % nm, [tor] + [tor + a for a in ARMS], [cl], [kit, cl], src="%s look with %s-jacket" % (p, j),
                               tier=_tier([kit, cl])))
    for j, nm in (("a", "I"), ("b", "II")):
        tor = "%s-%s-jacket-torso" % (p, j)
        kit = "%s-%s-jacket-kit" % (p, j)
        T["torso"].append(item("SHIRT %s" % nm, [tor] + [tor + a for a in ARMS], [], [kit], tier=_tier([kit]),
                               note="coat kit without its cloth prop; check in game that the sleeves read as a shirt"))
    cuts = (("pistol", "COAT, PISTOL CUT"), ("machete", "COAT, MACHETE CUT")) if sex == "m" else \
        (("pistol", "COAT, PISTOL CUT"), ("machete", "COAT, MACHETE CUT"), ("knife", "COAT, KNIFE CUT"))
    for c, label in cuts:
        cl = "%s-%s-jacket-cloth" % (p, c)
        tor = "%s-a-jacket-torso" % p
        paks = ["%s-a-jacket-kit" % p, cl]
        T["torso"].append(item(label, [tor] + [tor + a for a in ARMS], [cl], paks, tier=_tier(paks) if cl in MOD_PROPS else 2,
                               note="SP coat cloth pak with no look2-prop record: customize_looks copies the a-jacket-cloth prop's (MOD_PROPS)"))
    for k in ("01", "02"):
        tor = "scar-prisoner-%s-torso-%s" % (s, k)
        T["torso"].append(item("PRISONER SHIRT %s" % ("I" if k == "01" else "II"), [tor], paks=[tor + "-crowd"], src="scar-prisoner-%s-%s" % (s, k),
                               tier=3, note="only the -crowd pak ships (80-joint crowd rig): retarget to the base skeleton"))
    if sex == "m":
        for nm, part, sk in (("BRUTE JACKET", "scar-brute-male-01-torso", "base-brute-male-skel x1.1"),
                             ("TORTURED", "scar-tortured-male-body-01", "base-male-skel, body part (torso + legs)"),
                             ("ELDER (COLIN)", "scar-colin-body", "scar-colin-skel"),
                             ("ELDER (REUBEN)", "scar-reuben-body", "scar-reuben-skel"),
                             ("ISLANDER (CHRIS)", "scar-chris-body", "scar-chris-skel")):
            T["torso"].append(item(nm, [part], paks=[part], tier=3 if "base-male" not in sk else 2, note=sk))
        # (scar-jeremy-body / scar-mother-body: look2 parts exist but no pak ships them, so they are not listed)
    else:
        for nm, part, sk in (("BRUTE JACKET", "scar-brute-female-01-torso", "base-brute-female-skel x1.1"),
                             ("ISLANDER (EMILY)", "scar-emily-body", "scar-emily-skel")):
            T["torso"].append(item(nm, [part], paks=[part], tier=3, note=sk))
    _ported(T, sex)
    for legs, label in (("a", "TROUSERS A"), ("b", "TROUSERS B")) + ((("c", "TROUSERS C"),) if sex == "m" else ()):
        lp = "%s-%s-legs" % (p, legs)
        paks = ["%s-%s-legs-kit" % (p, legs)]
        T["lower"].append(item(label, [lp] + [lp + x for x in LEGS], paks=paks, tier=_tier(paks)))
    for k in ("01",):                                   # (02 = 01's card)
        lp = "scar-prisoner-%s-legs-%s" % (s, k)
        T["lower"].append(item("PRISONER TROUSERS", [lp], paks=[lp + "-crowd"], tier=3,
                               note="only the -crowd pak ships: retarget"))
    bag = "scar-t2r-bp-rigged" if sex == "m" else "scar-female-backpack"
    T["backpack"].append(item("SATCHEL", [bag], paks=[bag], tier=_tier([bag])))
    # (repeating ones skipped: the brute pack is the satchel again on the card: no row)
    # (the game has ONE Seraphite bag - the brutes' and the crowd's are
    # the same model. The archers' quiver (scar-male-quiver / scar-female-quiver) is no bag)
    for k in range(1, (13 if sex == "m" else 11) + 1):
        if (sex, k) == ("f", 1):                        # (female head 01 = head 11 on the card, rms 0.005)
            continue
        h = "%s-head-%02d" % (p, k)
        T["face"].append(item("FACE %02d" % k, [h], paks=[h], src="%s-%02d" % (p, k), tier=_tier([h])))
    _scar_names(T, sex)
    return T


# ------------------------------------------------------------------ card pictures (the item previews are render
# pictures like the No Return skin cards). tools/models/customize_cards.py renders each item's parts out of the game paks into
# re/icons/customize/cards/<slug>.png (300 x 275, the card); the header names the picture per item (cz_item_t.pic), the ext shows it
# on the card, an item without one shows its category icon. The slug comes from the parts, so a list edit never mixes pictures up.
CARD_DIR = os.path.join(ROOT, "re", "icons", "customize", "cards")
RIGGED_SRC = {"scar-t2r-bp-rigged": "scar-male-backpack", "militia-t2r-bp-rigged-11": "militia-male-backpack-11",
              "militia-t2r-bp-rigged-12": "militia-male-backpack-12"}       # mod-built rigged bags = dc_data_patches BACKPACK_RIG sources


GASMASK_HEAD = {"m": "militia-male-04-kit", "f": "militia-female-02-kit"}
MASK_HEAD = {"scar-t2r-mask01-kit": "scar-male-head-13", "scar-t2r-mask02-kit": "scar-male-head-06", "scar-t2r-mask03-kit": "scar-female-head-11"}


CARD_SLUG_MAX = 80                       # the longest card image name ("czc-" + slug) stays under 96 characters


# KELLIE's ears and legs rows keep the pictures from when each was a pak of its own (t2r-kl-f-ears, t2r-kl-f-legs-striped /
# -black). Since the size cut they are parts of ONE pak (t2r-kl-f-legs): by paks the ears row got the legs pak's name and both legs
# rows the same one, and none of the three names had a picture. The card renderer
# picks submeshes of a pak's first geometry, not parts - a new render of these three needs part selection first (their thigh
# holster of the earlier build is not on the legs pictures).
KELLIE_CARDS = {"KELLIE EARS": "t2r-kl-f-ears", "KELLIE STRIPED": "t2r-kl-f-legs-striped-skip-holster", "KELLIE BLACK": "t2r-kl-f-legs-black-skip-holster"}


def card_spec(cat, it):
    """(slug, [(pak, only, skip), ...]) for the item's card render, None for an item without parts to render (NONE, sex).
    only / skip: substrings of the full submesh name (customize_card_render.load)."""
    paks = it["paks"]
    if it["label"] in KELLIE_CARDS:
        return KELLIE_CARDS[it["label"]], [(paks[0], "", "")]
    if cat == "melee":      # FISTS: two posed forearms + hands (tools/models/customize_fists.py), KNIFE: Mel's survival knife = the knife the MP girls hold (knife-survival-mel, dc_data_patches.FEMALE_KNIFE_ADDS)
        return {"FISTS": ("melee-fists", [("@fists", "", "")]), "KNIFE": ("melee-knife", [("knife-survival-mel", "", "")])}.get(it["label"])
    if cat == "sex" or not paks:
        return None
    if cat in ("hat", "mask"):
        if it.get("halfmask"):          # the per-face cloth on its own head (the json's first face of that sex)
            sx = "f" if paks[0].startswith("scar-t2r-hff") else "m"
            key = HALFMASK_CARD[sx] if HALFMASK_CARD[sx] in HALFMASK["parts"] else next(k for k, (a, _p) in HALFMASK["parts"].items() if a.startswith("scar-t2r-hf" + sx))
            a, prt = HALFMASK["parts"][key]
            head = HALFMASK.get("heads", {}).get(key)
            spec = ([(head, "head_grp" if head.endswith("-kit") else "", "")] if head else []) + [(a, halfmask_slot(key), "")]
            slug = re.sub(r"[^a-z0-9]+", "-", "halfmask-" + a + "-" + key).strip("-")
            return slug, spec
        mk = next((x for x in paks if x.startswith("scar-t2r-mask")), None)
        if mk:              # the half mask = the kerchief of the mod-built kit (winter build) on the pool head it was shrink-wrapped to
            return re.sub(r"[^a-z0-9]+", "-", MASK_HEAD[mk] + "--" + mk + "-only-kerchief").strip("-"), \
                [(MASK_HEAD[mk], "", ""), (mk, "kerchief", "")]
        if paks[0].startswith("t2r-gm-"):      # a story gas mask: on the militia head of its preview (a mask alone reads as a strap tangle)
            spec = [(GASMASK_HEAD[paks[0][7]], "head_grp", ""), (paks[0], "", "")]
        elif any("hood" in x for x in paks):
            pk = next(x for x in paks if x.endswith("-hoodup" if it["label"] == "HOOD UP" else "-hooddown"))
            spec = [(pk, "", "")]
        else:
            spec = [(paks[0], "", "")]
    elif cat == "torso":
        spec = [(x, "", "head_grp") if x.endswith("-kit") else (x, "", "") for x in paks
                if not (x.startswith(("scar-t2r-skn-", "scar-t2r-hand")) and x not in PORTED_SKIN_CARDS)]     # (a garment card: no arms in the sleeves)
    elif cat == "lower":
        spec = []
        hip = it.get("hip")                            # (the hip holster every row wears is not on the card: the cards show the trousers)
        for x in (paks[:-1] if hip else paks):
            if x.endswith("-1hmelee-holster") or any(y == x for y, _, _ in spec):
                continue
            spec.append((x, "", "") if "-legs" in x else (x, "holster", "torso"))      # the kit's holster, not its chest strap
        # a legs kit that carries its own holster (d-legs: holster_d) shows it only on the item that names it
        if not any("holster" in h and "1hmelee" not in h for h in (it["parts"][:-1] if hip else it["parts"])):
            spec = [(x, o, "holster") if "-legs" in x else (x, o, k) for x, o, k in spec]
    elif cat == "backpack":
        spec = [(RIGGED_SRC.get(paks[0], paks[0]), "", "")]
    elif cat == "face":
        _fp = HEAD_SRC.get(paks[0], paks[0])           # (a bare-head copy: the stock head's picture)
        spec = [(_fp, "head_grp", "")] if _fp.endswith("-kit") else [(_fp, "", "")]
    else:
        return None
    slug = "--".join(x + ("-only-" + o if o else "") + ("-skip-" + k if k else "") for x, o, k in spec)
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
    if len(slug) > CARD_SLUG_MAX:          # (a six-pak item: a 200 character image name; in A/B its tile showed another tile's picture)
        import hashlib
        slug = slug[:CARD_SLUG_MAX - 9] + "-" + hashlib.md5(slug.encode()).hexdigest()[:8]
    return slug, spec


def card_pic(cat, it):
    cs = card_spec(cat, it)
    return "czc-" + cs[0] if cs and os.path.exists(os.path.join(CARD_DIR, "czc-" + cs[0] + ".png")) else None


# KELLIE (the developer's own character as CUSTOMIZE rows of the female lists of both factions - locked to the owner:
# the name is KELLIE and the requirement is BE KELLIE; the KELLIE face shows locked to others but the items do not show
# to them at all in the other categories). The models are made separately; this side reads ONE list file:
#   tools/models/data/kellie_rows.json = {"paks": {pak: [bytes, sha1]},
#       "rows": [{"fac": "wlf"|"scar", "sex": "f", "cat": "face"|"hat"|"torso"|"lower", "label": "...", "hidden": 0|1,
#                 "parts": [...], "props": [...], "paks": [...], "hide": [...],
#                 "templates": {part or prop: the stock look part / prop whose look2 record it copies}}]}
# and the pak files in KELLIE_DIR. Rows go LAST in their lists (indices are the identity on file and on the wire; a hidden row exists in
# every table and is only not listed for other accounts: customize.c cz_listed). All rows carry the exclusive kind "kellie" (plain line,
# no bar, off the CHALLENGES page; the owner test is customize.c cz_is_kellie). ON when the file and every listed pak are there;
# T2R_CZ_KELLIE=0 = off.
KELLIE_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "data", "kellie_rows.json")
KELLIE_DIR = os.environ.get("T2R_CZ_KELLIE_DIR", "../t2r-wt/cz-kellie")


def _kellie():
    if os.environ.get("T2R_CZ_KELLIE", "1") == "0" or not os.path.exists(KELLIE_LIST):
        return None
    import json
    k = json.load(open(KELLIE_LIST))
    for a, (size, _sha) in k["paks"].items():
        f = os.path.join(KELLIE_DIR, a + ".pak")
        if not os.path.exists(f) or os.path.getsize(f) != size:
            return None
    return k


KELLIE = _kellie()
if KELLIE:
    MP_PAKS_NOW |= set(KELLIE["paks"])
    for _r in KELLIE["rows"]:
        for _n, _tpl in _r.get("templates", {}).items():
            _pak = next((p for p in _r["paks"] if _n == p or (p.endswith("-kit") and _n.startswith(p[:-4])) or _n.startswith(p)), _r["paks"][0])
            (MOD_PROPS if _n in _r.get("props", ()) else MOD_PARTS)[_n] = (_pak, _tpl)


# WLF HEADWEAR out of NPC heads (beanies and the Jackson cowboy hats become pickable headwear): the Jackson
# riders' hats and the militia / Jackson / Firefly beanies are sub-meshes of head parts; tools/models/head_hats.py makes each a part of
# its own for both sexes (host = the head's pak, the hat on headb, pushed out of every list face's hair) and lists them in
# tools/models/data/head_hats.json; the prebuilt files are in HATS_DIR (staged by build_dll.stage_hats). Rows go after the stock
# headwear, before the KELLIE rows. T2R_CZ_HATS=0 = off.
HATS_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "data", "head_hats.json")
HATS_DIR = os.environ.get("T2R_CZ_HATS_DIR", "../t2r-wt/cz-hats6")      # (cz-hats: the first, larger fit; cz-hats2: FACE 10 without hair; cz-hats3: no male head copies; cz-hats4: the hats' fit folded two crowns)
HAT_TEMPLATE = {"m": "militia-male-hat-08", "f": "militia-female-hat-13"}      # the look2-mesh record a hat part copies


def _hats():
    if os.environ.get("T2R_CZ_HATS", "1") == "0" or not os.path.exists(HATS_LIST):
        return None
    import json
    k = json.load(open(HATS_LIST))
    # T2R_CZ_HEAD_SEXES (default "fm"): which sexes' bare-head copies ship. An in-image test build has no room for the six male
    # copies (+21 MB packed): "f" leaves them out - the male faces then wear their stock heads; the side-file build takes all.
    sexes = os.environ.get("T2R_CZ_HEAD_SEXES", "fm")
    for h in [h for h in k.get("heads", ()) if h["sex"] not in sexes]:
        k["heads"].remove(h)
        k["paks"].pop(h["pak"], None)
        k["paks"].pop((h.get("hair") or {}).get("pak"), None)
    for a, (size, _sha) in k["paks"].items():
        f = os.path.join(HATS_DIR, a + ".pak")
        if not os.path.exists(f) or os.path.getsize(f) != size:
            return None
    return k


HATS = _hats()
# THE HATS PUSHED OFF THE LIST HEADS' SKIN (cz-hats7, tools/models/hat_skin_fit.py: BALL CAP sat inside the forehead of every
# face but its own, the beanies lay within a millimetre of the skin above the ear). tools/models/data/hat_skin_fit.json lists the
# paks that moved: the cz-hats ones (they take the place of HATS_DIR's files, same names) and "stock" = the game's own caps that
# moved (staged under their own names: they replace the game's pak in the mod data, no new actor). T2R_CZ_HATS_FIT=0 = off.
HATS_FIT_LIST = os.path.join(os.path.dirname(HATS_LIST), "hat_skin_fit.json")
HATS_FIT_DIR = os.environ.get("T2R_CZ_HATS_FIT_DIR", "../t2r-wt/cz-hats12")    # (cz-hats7: bare skin; cz-hats8: + room for KELLIE under five female hats; cz-hats9: 3 mm over every head; cz-hats10: brimmed hats 2.5 mm, no flipped triangle; cz-hats11: brimmed hats in 1.5 mm steps; cz-hats12: bare skin counted too - ear tips through two men's hats)


def _hats_fit():
    if not HATS or os.environ.get("T2R_CZ_HATS_FIT", "1") == "0" or not os.path.exists(HATS_FIT_LIST):
        return None
    import json
    k = json.load(open(HATS_FIT_LIST))
    for a, (size, _sha) in k["paks"].items():
        f = os.path.join(HATS_FIT_DIR, a + ".pak")
        if not os.path.exists(f) or os.path.getsize(f) != size:
            return None
    return k


HATS_FIT = _hats_fit()
# the cap-only heads as heads that can be worn bare (tools/models/head_fix.py, head_hats.json "heads"; faces 10, 13
# and 15 had dark hairlines): a copy of the head with the cap's shadow off and
# the soldier's grime down, as a part of its own in a pak of its own. Its FACE row wears the copy; the look2 record is a copy of the
# stock head's; the card picture stays the stock head's (HEAD_SRC).
HEAD_FIX, HEAD_SRC = {}, {}
if HATS:
    MP_PAKS_NOW |= set(HATS["paks"])
    for _r in HATS["rows"]:
        MOD_PARTS[_r["part"]] = (_r["pak"], HAT_TEMPLATE[_r["sex"]])
    for _h in HATS.get("heads", ()):
        HEAD_FIX[(_h["sex"], _h["kit"])] = _h
        HEAD_SRC[_h["pak"]] = _h["of_pak"]
        MOD_PARTS[_h["part"]] = (_h["pak"], _h["of"])
        if _h.get("hair"):                             # (its look2 record: a hat's, as KELLIE's crown hair parts)
            MOD_PARTS[_h["hair"]["part"]] = (_h["hair"]["pak"], HAT_TEMPLATE[_h["sex"]])


# HAT-FITTED FACES (all headwear fits on the other faces too): the hair of a
# list face stands through the hats (measured there: every one of the 29 faces with hair). A face can have a second, hat-fitted
# part - a copy of its head (or of its hair part) with the hair pressed under the shell of every crown-covering hat of its list
# (facefix.py). The FACE row then wears [its stock part(s), the fitted part]; headwear that covers the
# crown hides the STOCK part, every other headwear row hides the fitted one - so the bare-headed look stays the stock head.
# The list: tools/models/data/face_fit.json (tools/models/face_fit_import.py: paks + sha1 out of the source json into
# FACEFIT_DIR). No file / T2R_CZ_FACEFIT=0 = no fitted faces. "first": the pak's actor stands BEFORE its stock pak in the level
# list (the test of a copy whose shader blobs are zeroed).
FACEFIT_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "data", "face_fit.json")
FACEFIT_DIR = os.environ.get("T2R_CZ_FACEFIT_DIR", "../wt/t2r-prebuilt/cz-facefit4")       # (2: "plan B", 13 WLF faces whose head is the stock kit's - f 01 02 03 04 05 06 07 09 14, m 04 06 12 16 - as head-only paks, 4 geometry items each)


def _facefit():
    if os.environ.get("T2R_CZ_FACEFIT", "1") == "0" or not os.path.exists(FACEFIT_LIST):
        return []
    import json
    k = json.load(open(FACEFIT_LIST))["faces"]
    for r in k:
        f = os.path.join(FACEFIT_DIR, r["pak"] + ".pak")
        if not os.path.exists(f) or os.path.getsize(f) != r["bytes"]:
            return []
    return k


FACEFIT = _facefit()
# HAIR AS PARTS INSIDE THE BARE-HEAD COPIES ("plan A", the nine copy faces must have fitted hair under hats before the
# release): tools/models/hair_parts_import.py -> data/hair_parts.json + the prebuilt paks in HAIRPARTS_DIR. Each pak has the NAME
# of a cz-hats bare-head copy and replaces it (build_dll.stage_hairparts, after stage_hats): bald head part + the hair twice in
# the pak's unused geos - "bare" (stock shape) and "hat" (pressed under the hats). The FACE row wears head + both hair sets; the
# headwear rows hide one of them: a crown hat hides the bare set, every other row (NONE too) the hat set. 0 new actors, 0 new
# geometry slots. No file / T2R_CZ_HAIRPARTS=0 = the cz-hats copies with their own hair, as before.
HAIRPARTS_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "data", "hair_parts.json")
HAIRPARTS_DIR = os.environ.get("T2R_CZ_HAIRPARTS_DIR", "../wt/t2r-prebuilt/cz-hairparts5")       # (4 = the first set, slimmed by hair_parts_import --slim: 12 - 16 geometry items a pak, 100 in all against the copies' 196. A slim pak on a character kit is NOT proven on a client before build #21)


def _hairparts():
    # (on build #22, male faces 02 / 03 / 05 / 14 / 17 - exactly the hair-part faces - the
    #  hair cards draw as opaque shards, also under the BALL CAP. The male ones are off by default: those faces are the cz-hats copies
    #  with their own hair, as before. T2R_CZ_HAIRPARTS = the sexes that get them: "f" (default), "fm" = all, "0" = none.)
    sexes = os.environ.get("T2R_CZ_HAIRPARTS", "f")
    sexes = "fm" if sexes == "1" else "" if sexes == "0" else sexes
    if not sexes or not os.path.exists(HAIRPARTS_LIST):
        return []
    import json
    k = [r for r in json.load(open(HAIRPARTS_LIST))["faces"] if r["sex"] in sexes]
    for r in k:
        for a, size in [(r["pak"], r["bytes"])] + [(e["pak"], e["bytes"]) for e in r.get("extra_paks", ())]:
            f = os.path.join(HAIRPARTS_DIR, a + ".pak")
            if not os.path.exists(f) or os.path.getsize(f) != size:
                return []
    return k


def hair_part_pak(r, part):
    """the pak of a hair part of a hair_parts.json face: its own pak or one of its extra paks (part name = <pak without -kit>-...)"""
    for a in [r["pak"]] + [e["pak"] for e in r.get("extra_paks", ())]:
        if part.startswith(a[:-4] + "-"):
            return a
    raise AssertionError("hair_parts.json: %s %s part %s is in none of its paks" % (r["sex"], r["face"], part))


def hair_parts_all(r):
    """every hair part of a face: bare + the old shared hat set + one set per crown hat ("per_hat")"""
    return list(r["bare"]) + list(r["hat"]) + [x for v in r.get("per_hat", {}).values() for x in v]


HAIRPARTS = _hairparts()
# (per hat everywhere (each headwear, not by type), LOD0 only: "per_hat" =
#  {crown hat label: [parts]}, the groomed hair under exactly that hat, in the face's pak and its "extra_paks" - copies of the same
#  kit, NEW actors. A crown hat row hides the bare set and every per-hat part but its own; any other row hides every per-hat part.)
for _r in HAIRPARTS:
    for _p in hair_parts_all(_r):                       # (their look2 records: copies of a hat part's, as KELLIE's crown hair)
        MOD_PARTS[_p] = (hair_part_pak(_r, _p), HAT_TEMPLATE[_r["sex"]])
    for _e in _r.get("extra_paks", ()):
        MP_PAKS_NOW.add(_e["pak"])
for _c, (_pk, _st) in HANDTINT_PARTS.items():          # (a hand-tint copy's part: its stock part's record; the tint key is customize_looks')
    MOD_PARTS[_c] = (_pk, _st)
    MP_PAKS_NOW.add(_pk)
for _r in FACEFIT:
    # (the look2 record a fitted part copies: its stock part's - or, for a stock part that is itself a mod part, that part's template)
    MOD_PARTS[_r["part"]] = (_r["pak"], MOD_PARTS[_r["stock_part"]][1] if _r["stock_part"] in MOD_PARTS else _r["stock_part"])
    MP_PAKS_NOW.add(_r["pak"])


# Rows held out of the lists until they are right in game (final labels). The first time the rebuilt Seraphite tops were worn
# in game: the SP coat cuts (holster strap / machete sling / knife strap cloth paks) draw MISSING MATERIAL or another colour than the
# kit - their own kits are not in the level. (The tops with skin_tint.py paks were held too until mesh_replace wrote the skin block's
# influence count right: tools/models/skin_pak_check.py.) The paks stay in the build; a row comes back by leaving this table.
# The first build with the face palettes (hands follow the face on every other top): the tops whose bare skin is an atlas
# of the garment's own maps (ragged / torn / shirtless) drew that skin WHITE, and ELDER'S HOODED COAT / ISLANDER LONG COAT drew without
# the coat. Both found and back in the lists: skin_tint.py gave other materials' descriptors the atlas' hash (the engine drew the
# first: a pale 64 px stub), and the two raincoat cloths had no props.bin definition (dc_data_patches.customize_prop_copies).
HELD = {
    # (Tan Raincoat of the male Seraphites removed, Weathered Raincoat made the default instead)
    ("scar", "m"): ("RAINCOAT, HOLSTER STRAP", "RAINCOAT, MACHETE SLING", "TAN RAINCOAT"),
    # (leather raincoat removed, worn leather raincoat made the default)
    ("scar", "f"): ("SHIRT, HOLSTER STRAP", "SHIRT, MACHETE SLING", "RAINCOAT, KNIFE STRAP", "LEATHER RAINCOAT"),
}


def table():
    out = {}
    for fac in FACTIONS:
        for sex in SEXES:
            T = _wlf(sex) if fac == "wlf" else _scar(sex)
            for c in CATS:
                if c in T:
                    T[c] = [it for it in T[c] if it["label"] not in HELD.get((fac, sex), ())]
            for r in (HATS["rows"] if HATS and fac == "wlf" else ()):
                if r["sex"] == sex:
                    T["hat"].append(item(r["label"], [r["part"]], paks=[r["pak"]], tier=_tier([r["pak"]]),
                                         src="%s out of a head part (tools/models/head_hats.py)" % r["code"]))
            for r in (KELLIE["rows"] if KELLIE else ()):          # last in their lists (hidden rows must be)
                if (r["fac"], r["sex"]) == (fac, sex):
                    it = item(r["label"], r["parts"], r.get("props", ()), r["paks"], tier=_tier(r["paks"]), hide=r.get("hide", ()))
                    it["hid"] = 1 if r.get("hidden") else 0
                    T[r["cat"]].append(it)
            # KELLIE's crown hair is parts of her FACE row ("headwear_hides", "hair_groups" below; "i want to be able to pick
            # other headwear too ... i want the clipping to be fixed", then "putting on a gasmask hides the hair piece so it looks
            # weird, it should be just like how ellies hair reacts to a gas mask"): A = the free crown, B = the crown as it lies under
            # a gas mask's straps. Exactly one of them is drawn, or none - as hide lists: headwear that covers the crown (caps, hats,
            # beanies, the raised hood) hides A and B; a gas mask (the bong too) hides A; every other MASK row (NONE, the half masks)
            # hides B; NONE / KELLIE EARS / the hood on the back hide nothing. On another face the hides do nothing (the parts are
            # not in the outfit). The json and these rules go into a build together: A and B drawn at once = two crowns.
            # (kellie_rows.json "hair_groups"): the two crown parts became ten - the bare crown (A), the crown
            # under a gas mask's straps (B), and per headwear group (caps, cowboy hats, beanies, the raised hood) one hair part pressed
            # under that group's shells plus its gas mask shape. Exactly one of the ten is drawn per headwear x mask (the head kit's
            # own hair always draws): a hat row of group G hides all but set[G] and set_gasmask[G]; a crown-free hat row (NONE,
            # KELLIE EARS, HOOD DOWN) hides the eight group parts; a gas mask row hides A and the four plain group parts; any other
            # mask row (NONE, HALF MASK) hides B and the four gas mask group parts. A row the lists do not name stops the build: an
            # unclassified headwear would draw two crowns or none.
            _hg = (KELLIE or {}).get("hair_groups") if sex == "f" else None
            if _hg:
                def _add(it, parts):
                    it["hide"] = list(it.get("hide", ())) + [x for x in parts if x and x not in it.get("hide", ())]
                _set, _setm = _hg["set"], _hg["set_gasmask"]
                _all = [_hg["bare"], _hg["masked"]] + [_set[g] for g in _set] + [_setm[g] for g in _setm]
                _grp = {lab: g for g, labs in _hg["hats"].items() for lab in labs}
                for it in T["hat"]:
                    g = _grp.get(it["label"])
                    if g is not None:
                        _add(it, [x for x in _all if x not in (_set[g], _setm[g])])
                    else:
                        assert it["label"] in _hg["crown_free_hats"], "kellie_rows.json hair_groups: %s %s hat row %r is in no hair group" % (fac, sex, it["label"])
                        _add(it, list(_set.values()) + list(_setm.values()))
                for it in T["mask"]:
                    gas = it["label"] in _hg["gas_masks"]
                    assert gas or it["label"] in _hg["plain_masks"], "kellie_rows.json hair_groups: %s %s mask row %r is in no mask list" % (fac, sex, it["label"])
                    _add(it, [_hg["bare"]] + list(_set.values()) if gas else [_hg["masked"]] + list(_setm.values()))
            fits = []                                  # (stock part, fitted part) of this list's hat-fitted faces
            for r in FACEFIT:
                if (r["fac"], r["sex"]) != (fac, sex):
                    continue
                it = next((x for x in T["face"] if r["stock_part"] in x["parts"]), None)
                assert it, "face_fit.json: no %s %s FACE row wears %s" % (fac, sex, r["stock_part"])
                it["parts"].append(r["part"])
                it["paks"].append(r["pak"])
                it["tier"] = _tier(it["paks"])
                fits.append((r["stock_part"], r["part"]))
            for it in T["hat"] if fits else ():
                crown = any("-hat-" in p or p.startswith("t2r-hw-") for p in it["parts"]) or any(h.endswith("-hooddown") for h in it.get("hide", ()))
                hd = [s if crown else f for s, f in fits]
                it["hide"] = list(it.get("hide", ())) + [x for x in hd if x not in it.get("hide", ())]
            hsets = []                                 # (bare hair parts, hat hair parts) of this list's copy faces (HAIRPARTS)
            for r in HAIRPARTS:
                if (r["fac"], r["sex"]) != (fac, sex):
                    continue
                it = next((x for x in T["face"] if x["label"] == r["face"]), None)
                assert it and r["pak"] in it["paks"], "hair_parts.json: no %s %s %s row with the pak %s" % (fac, sex, r["face"], r["pak"])
                assert all(h in it["parts"] for h in r["head_parts"]), "hair_parts.json: %s %s %s does not wear %s" % (fac, sex, r["face"], r["head_parts"])
                it["parts"] += [x for x in hair_parts_all(r) if x not in it["parts"]]
                it["paks"] += [e["pak"] for e in r.get("extra_paks", ()) if e["pak"] not in it["paks"]]
                it["tier"] = _tier(it["paks"])
                hsets.append((r["bare"], r["hat"], r.get("per_hat", {}), r["face"]))
            for it in T["hat"] if hsets else ():
                crown = any("-hat-" in p or p.startswith("t2r-hw-") for p in it["parts"]) or any(h.endswith("-hooddown") for h in it.get("hide", ()))
                hd = []
                for bare, hat, per_hat, face in hsets:
                    if per_hat and crown:
                        assert it["label"] in per_hat, "hair_parts.json: %s %s %s has no per-hat hair for the crown row %r" % (fac, sex, face, it["label"])
                    own = per_hat.get(it["label"], []) if crown else []
                    hd += (bare if crown else hat) + [x for v in per_hat.values() for x in v if x not in own]
                it["hide"] = list(it.get("hide", ())) + [x for x in hd if x not in it.get("hide", ())]
            if HALFMASK and T.get("mask"):             # PER-FACE HALF MASK: each FACE row wears its own cloth (hidden unless HALF MASK is picked)
                rows = HALFMASK["rows"].get("%s-%s" % (fac, sex), {})
                hm = []
                for it in T["face"]:
                    assert it["label"] in rows, "halfmask_faces.json: no cloth for %s %s %s" % (fac, sex, it["label"])
                    a, prt = rows[it["label"]]
                    it["parts"].append(prt)
                    if a not in it["paks"]:
                        it["paks"].append(a)
                    it["tier"] = _tier(it["paks"])
                    hm.append(prt)
                for it in T["mask"]:
                    if not it.get("halfmask"):
                        it["hide"] = list(it.get("hide", ())) + [x for x in hm if x not in it.get("hide", ())]
            if MASK_UNDER:                             # a gas mask and headwear: exactly one shape of the mask is drawn
                gas = [it for it in T["mask"] if it.get("under")]
                for it in T["hat"]:
                    crown = any("-hat-" in p or p.startswith("t2r-hw-") for p in it["parts"]) or any(h.endswith("-hooddown") for h in it.get("hide", ()))
                    small = any("-hat-" in p or (p.startswith("t2r-hw-") and p[9:11] in ("c1", "c2")) for p in it["parts"])
                    cls = None if not crown else MASK_UNDER[0] if len(MASK_UNDER) == 1 else "s" if small else "b"
                    hd = [u for g in gas for c, u in g["under"].items() if c != cls] + ([g["parts"][0] for g in gas] if crown else [])
                    it["hide"] = list(it.get("hide", ())) + [x for x in hd if x not in it.get("hide", ())]
            T["melee"] = [item("FISTS"), item("KNIFE")]
            T["sex"] = [item("MALE"), item("FEMALE")]
            out[(fac, sex)] = T
    _MAP_TURN[:] = [0, {}]
    for key, T in out.items():
        assign_unlocks(key, T)
    return out


# ------------------------------------------------------------------ unlocks (customization options are locked, the
# default should always be picked first, and then one by one customization options can be unlocked in different ways (survive 4/8/12
# weeks, win x on y map, unlock x safes in interrogation, reach rank 2..10, get revives, reach x survivors (hard numbers)))
# Basic challenges are not enough (eliminate x with y weapon, get x assists), so the
# challenges are a catalogue of named feats (U_CHAL), each with a title and a line, built on what the ext already counts per match:
# the clan state (weeks / rank / survivors), the award labels and down / execution counters of the daily missions (t2r-ext.c mis_book /
# mis_down_book, g_mis_cnt by mission label id = clan.py MISSIONS), a few more award labels booked for this (ids 54..63, U_LABELS), the
# match result (wins, flawless wins, wins per map), the best streak of a match and the best count of one match.
# Every item but its category's default carries ONE challenge. Down a list the challenges get harder (level 1 .. 10 spread over the
# list). Each category draws from its own themed pool (U_POOL: headwear = the eye (marks, headshots, range, the rifles, the bow);
# torso = the fight and the journey; lower = sidearms and backup; backpack = the carrier (gifts, heals, revives, throwables, safes);
# face = the gun executions and the moments a player is remembered for; melee = the knife is earned with the fists). SEX is never locked
# (who the player is, not a reward). Progress: customize.c + customize_core.h; re/customize-1117.md "Unlocks".
U_KINDS = ("weeks", "rank", "survivors", "safes", "mapwins", "wins", "matches", "flawless", "streak", "count", "best", "og", "kellie", "ach")   # CZK_*: index + 1
U_SCALAR = ("weeks", "rank", "survivors", "safes", "wins", "matches", "flawless", "streak", "og", "kellie")    # one number each (file: stat <kind> <n>)
U_PLAIN = ("og", "kellie", "ach")    # kinds that are no challenge: a plain line, no number, no bar, off the CHALLENGES page
# CLOTHING BY ACHIEVEMENT (some clothing is unlockable via achievements, and achievements show that
# UNLOCKS: X too): item label -> (achievement id of tools/achievements.py, its title). The item's line reads EARN THE ACHIEVEMENT
# <TITLE>; the ext asks the achievements code (achieve.c ach_earned) and, once earned, writes a "grant <label>" line into the
# profile, so the item stays open before the achievement table has arrived at the next start. tools/ext/customize_ach.h (--header)
# is the table the achievements page reads for its "UNLOCKS: <label>" line. No hidden achievement is used (its name must not show).
U_ACH = {
    "ISLANDER LONG COAT": ("bow_50", "ROBIN HOOD"),               # down 250 enemies with the bow
    "ELDER'S HOODED COAT": ("sera_12", "THE PROPHET PROVIDES"),   # survive 12 weeks as the Seraphites
    "M-65 JACKET": ("wlf_12", "WOLF PACK"),                       # survive 12 weeks as the WLF
    "TORTURED": ("lockbox_10", "SAFECRACKER"),                    # open 25 lockboxes in Interrogation
    "ABBY'S GAS MASK": ("se_hammer", "HAMMER TIME"),              # 50 special executions with a hammer in hand
}
U_NLEVEL = 10
# counted labels: id = the ext's per-match counter (g_mis_cnt index; 1..20 and 40..52 = the daily mission ids, 54..63 booked for this by
# mis_book from these award labels) -> file key. File: count <key> <n> (career total), best <key> <n> (the best one match).
U_LABELS = {1: "downs", 2: "executions", 3: "revives", 4: "headshots", 5: "marks", 6: "heals", 7: "special-executions", 8: "molotov-downs",
            9: "nail-bomb-downs", 10: "gifts", 11: "melee-downs", 12: "shiv-kills", 13: "long-range-downs",
            14: "downs-9mm", 15: "downs-revolver", 16: "downs-shorty", 17: "downs-hunting-rifle", 18: "downs-semi-auto", 19: "downs-burst-rifle",
            20: "downs-bow",
            40: "exec-variable-rifle", 41: "exec-hunting-rifle", 42: "exec-bow", 43: "exec-full-auto", 44: "exec-semi-auto", 45: "exec-tactical-shotgun",
            46: "exec-frontier-rifle", 47: "exec-burst-rifle", 48: "exec-9mm", 49: "exec-revolver", 50: "exec-burst-pistol", 51: "exec-enforcer",
            52: "exec-shorty",
            54: "assists", 55: "team-revenge", 56: "streaks-stopped", 57: "retaliations", 58: "rapid-kills", 59: "kills-while-hurt",
            60: "last-one-standing", 61: "crafts", 62: "interrogations-denied", 63: "marked-target-kills"}
# the award label each id 54..63 counts (t2r-ext.c mis_book; the ext pays them: ev_pay / lms.c / skills.c / interrogation.c)
U_AWARD_IDS = {"Assist": 54, "Team Revenge": 55, "Streak Stopped": 56, "Retaliation": 57, "Rapid Kill": 58, "Kill While Hurt": 59,
               "Last One Standing": 60, "Craft": 61, "Interrogation Denied": 62, "Marked Target Killed": 63}
_W = (10, 20, 35, 50, 75, 100, 150, 200, 300, 400)          # downs with one gun
_X = (3, 5, 10, 15, 20, 30, 40, 50, 75, 100)                # executions with one gun
_A = (5, 10, 20, 35, 50, 75, 100, 150, 200, 300)            # award feats
_B = (2, 3, 4, 5, 6, 7, 8, 10, 12, 15)                      # the best of one match
# key -> (kind, arg, title, line (%d = the number, %s = the map), numbers per level 1..10, lowest level it may sit at)
U_CHAL = {
    # the journey (clan state 0xE1, latched at the best reached)
    "weeks": ("weeks", 0, "THE LONG ROAD", "SURVIVE %d WEEKS", (4, 4, 4, 8, 8, 8, 12, 12, 12, 12), 1),
    "rank": ("rank", 0, "VETERAN", "REACH RANK %d", (2, 2, 2, 2, 2, 3, 4, 6, 8, 10), 5),
    # not a challenge: who played before the public release has it (customize.c cz_og_tick). No number, no bar; not on the CHALLENGES page
    "og": ("og", 0, "OG EXCLUSIVE", "FOR MY FELLOW STONERS THAT HELPED SHAPE THIS MOD", (1,) * 10, 1),
    "survivors": ("survivors", 0, "SAFE HAVEN", "REACH %d SURVIVORS", (10, 20, 30, 40, 50, 75, 100, 125, 150, 200), 1),
    "safes": ("safes", 0, "SAFECRACKER", "CRACK %d SAFES IN INTERROGATION", (1, 3, 5, 10, 15, 20, 30, 40, 50, 75), 1),
    # the match
    "mapwins": ("mapwins", 0, "HOME GROUND", "WIN %d MATCHES ON %s", (3, 5, 10, 15, 20, 25, 30, 40, 50, 60), 1),
    "wins": ("wins", 0, "WINNING SIDE", "WIN %d MATCHES", (5, 10, 25, 50, 75, 100, 150, 200, 300, 500), 1),
    "matches": ("matches", 0, "STILL HERE", "PLAY %d MATCHES", (5, 10, 25, 50, 100, 150, 200, 300, 400, 500), 1),
    "flawless": ("flawless", 0, "UNTOUCHED", "WIN %d MATCHES WITHOUT DYING", (1, 2, 3, 5, 8, 10, 15, 20, 25, 30), 2),
    "streak": ("streak", 0, "ON A ROLL", "DOWN %d ENEMIES WITHOUT DYING", (3, 4, 5, 6, 7, 8, 9, 10, 12, 15), 1),
    # career totals
    "downs": ("count", 1, "BODY COUNT", "DOWN %d ENEMIES", (25, 50, 100, 200, 300, 500, 750, 1000, 1500, 2000), 1),
    "executions": ("count", 2, "NO MERCY", "EXECUTE %d ENEMIES", (10, 25, 50, 100, 150, 250, 350, 500, 750, 1000), 1),
    "revives": ("count", 3, "NOBODY GETS LEFT BEHIND", "REVIVE %d TEAMMATES", (10, 25, 50, 75, 100, 150, 200, 300, 400, 500), 1),
    "headshots": ("count", 4, "STEADY HANDS", "DOWN %d ENEMIES WITH HEADSHOTS", (10, 25, 50, 100, 150, 200, 300, 400, 500, 750), 1),
    "marks": ("count", 5, "EYES ON THEM", "MARK %d ENEMIES", (25, 50, 100, 200, 300, 400, 500, 750, 1000, 1500), 1),
    "heals": ("count", 6, "FIELD MEDIC", "HEAL TEAMMATES %d TIMES", (5, 10, 25, 50, 75, 100, 150, 200, 300, 400), 1),
    "special-executions": ("count", 7, "MAKE IT PERSONAL", "LAND %d SPECIAL EXECUTIONS", (5, 10, 20, 35, 50, 75, 100, 150, 200, 300), 1),
    "molotov-downs": ("count", 8, "FIRESTARTER", "DOWN %d ENEMIES WITH MOLOTOVS", (3, 5, 10, 20, 30, 40, 50, 75, 100, 150), 1),
    "nail-bomb-downs": ("count", 9, "SHRAPNEL", "DOWN %d ENEMIES WITH NAIL BOMBS", (3, 5, 10, 20, 30, 40, 50, 75, 100, 150), 1),
    "gifts": ("count", 10, "SHARE THE LOAD", "GIVE %d CRAFTING ITEMS TO TEAMMATES", (3, 5, 10, 20, 30, 40, 50, 75, 100, 150), 1),
    "melee-downs": ("count", 11, "BARE KNUCKLES", "DOWN %d ENEMIES IN MELEE", (5, 10, 25, 50, 75, 100, 150, 200, 300, 400), 1),
    "shiv-kills": ("count", 12, "QUIET WORK", "SHIV %d ENEMIES", (1, 3, 5, 10, 15, 25, 35, 50, 75, 100), 1),
    "long-range-downs": ("count", 13, "FROM AFAR", "DOWN %d ENEMIES FROM 30 M OR MORE", (5, 10, 20, 35, 50, 75, 100, 150, 200, 300), 1),
    "downs-9mm": ("count", 14, "SIDEARM", "DOWN %d ENEMIES WITH THE 9MM PISTOL", _W, 1),
    "downs-revolver": ("count", 15, "SIX CHAMBERS", "DOWN %d ENEMIES WITH THE REVOLVER", _W, 1),
    "downs-shorty": ("count", 16, "POINT BLANK", "DOWN %d ENEMIES WITH THE SHORTY", _W, 1),
    "downs-hunting-rifle": ("count", 17, "ONE BREATH", "DOWN %d ENEMIES WITH THE HUNTING RIFLE", _W, 1),
    "downs-semi-auto": ("count", 18, "MARKSMAN", "DOWN %d ENEMIES WITH THE SEMI-AUTO RIFLE", _W, 1),
    "downs-burst-rifle": ("count", 19, "THREE-ROUND BURST", "DOWN %d ENEMIES WITH THE BURST RIFLE", _W, 1),
    "downs-bow": ("count", 20, "SILENT STRING", "DOWN %d ENEMIES WITH THE BOW", _W, 1),
    "exec-variable-rifle": ("count", 40, "CLOSE THE DISTANCE", "EXECUTE %d ENEMIES WITH THE VARIABLE RIFLE", _X, 1),
    "exec-hunting-rifle": ("count", 41, "ONE LAST LOOK", "EXECUTE %d ENEMIES WITH THE HUNTING RIFLE", _X, 1),
    "exec-bow": ("count", 42, "THE OLD WAYS", "EXECUTE %d ENEMIES WITH THE BOW", _X, 1),
    "exec-full-auto": ("count", 43, "SUPPRESSIVE FIRE", "EXECUTE %d ENEMIES WITH THE FULL-AUTO RIFLE", _X, 1),
    "exec-semi-auto": ("count", 44, "MEASURED", "EXECUTE %d ENEMIES WITH THE SEMI-AUTO RIFLE", _X, 1),
    "exec-tactical-shotgun": ("count", 45, "BREACHER", "EXECUTE %d ENEMIES WITH THE TACTICAL SHOTGUN", _X, 1),
    "exec-frontier-rifle": ("count", 46, "FRONTIER JUSTICE", "EXECUTE %d ENEMIES WITH THE FRONTIER RIFLE", _X, 1),
    "exec-burst-rifle": ("count", 47, "DISCIPLINE", "EXECUTE %d ENEMIES WITH THE BURST RIFLE", _X, 1),
    "exec-9mm": ("count", 48, "STANDARD ISSUE", "EXECUTE %d ENEMIES WITH THE 9MM PISTOL", _X, 1),
    "exec-revolver": ("count", 49, "HIGH NOON", "EXECUTE %d ENEMIES WITH THE REVOLVER", _X, 1),
    "exec-burst-pistol": ("count", 50, "DOUBLE TAP", "EXECUTE %d ENEMIES WITH THE BURST PISTOL", _X, 1),
    "exec-enforcer": ("count", 51, "ENFORCER", "EXECUTE %d ENEMIES WITH THE ENFORCER", _X, 1),
    "exec-shorty": ("count", 52, "SAWN OFF", "EXECUTE %d ENEMIES WITH THE SHORTY", _X, 1),
    "assists": ("count", 54, "GOT YOUR BACK", "EARN %d ASSISTS", (10, 25, 50, 100, 150, 200, 300, 400, 500, 750), 1),
    "team-revenge": ("count", 55, "SETTLE THE SCORE", "AVENGE %d DOWNED TEAMMATES", _A, 1),
    "streaks-stopped": ("count", 56, "NOT TODAY", "END %d ENEMY KILL STREAKS", (1, 2, 3, 5, 8, 10, 15, 20, 25, 30), 2),
    "retaliations": ("count", 57, "EYE FOR AN EYE", "DOWN THE ENEMY WHO DOWNED YOU %d TIMES", _A, 1),
    "rapid-kills": ("count", 58, "IN QUICK SUCCESSION", "DOWN TWO ENEMIES WITHIN 10 SECONDS %d TIMES", (3, 5, 10, 20, 30, 50, 75, 100, 150, 200), 1),
    "kills-while-hurt": ("count", 59, "BLEEDING, NOT BEATEN", "DOWN %d ENEMIES WHILE BADLY HURT", _A, 1),
    "last-one-standing": ("count", 60, "LAST ONE STANDING", "BE YOUR TEAM'S LAST ONE STANDING %d TIMES", (1, 3, 5, 10, 15, 20, 30, 40, 50, 75), 1),
    "crafts": ("count", 61, "MAKESHIFT", "CRAFT %d ITEMS", (10, 25, 50, 100, 150, 250, 350, 500, 750, 1000), 1),
    "interrogations-denied": ("count", 62, "NOT ONE WORD", "DENY %d INTERROGATIONS", (1, 3, 5, 10, 15, 20, 30, 40, 50, 75), 1),
    "marked-target-kills": ("count", 63, "OVERWATCH", "LET YOUR TEAM DOWN %d ENEMIES YOU MARKED", (10, 25, 50, 100, 150, 200, 300, 400, 500, 750), 1),
    # the best of one match
    "best-downs": ("best", 1, "ONE-MAN ARMY", "DOWN %d ENEMIES IN ONE MATCH", (5, 6, 7, 8, 9, 10, 12, 14, 16, 20), 1),
    "best-executions": ("best", 2, "NO WITNESSES", "EXECUTE %d ENEMIES IN ONE MATCH", _B, 1),
    "best-revives": ("best", 3, "GUARDIAN ANGEL", "REVIVE %d TEAMMATES IN ONE MATCH", _B, 1),
    "best-headshots": ("best", 4, "SURGICAL", "DOWN %d ENEMIES WITH HEADSHOTS IN ONE MATCH", _B, 1),
    "best-assists": ("best", 54, "FORCE MULTIPLIER", "EARN %d ASSISTS IN ONE MATCH", (3, 4, 5, 6, 7, 8, 10, 12, 14, 16), 1),
}
# The numbers (the challenges for clothes were very
# inconsistent, e.g. LET YOUR TEAM DOWN 500 ENEMIES YOU MARKED for one gas mask; they should not be too tedious but not too easy either): every ladder above was written by hand on its own scale, and
# the last row of a list always sits at level 10 - 500 marked downs next to 5 wins. Now ONE effort ladder: an item of level 1..10 costs
# U_EFFORT matches of ordinary play, and a counter's number = its usual count per match (U_RATE) x that. The top of every list is 18
# matches; the rates are our estimate for a 4v4 match and the one place to tune. U_FIXED: feats that are not "how often" (the best of one
# match, a streak, the clan's state, a win on one map) keep a short hand-written ladder in the same spirit.
# (the first ladder (1 .. 18 matches) was too easy, e.g. 2 executions with the enforcer; the balance should be fun, not
# too easy, harder for the cooler ones: the plainest item now costs three matches of its feat, the top ones 26)
# (on 3 .. 26: too many items could unlock from one match, and everyone would have everything
# unlocked after just passing 12 weeks - a journey is 84 matches: the plainest item now costs six matches of its feat, the top ones 90,
# and the feats are different ones, so nobody works on all of them at once)
U_EFFORT = (6, 9, 13, 18, 25, 34, 45, 58, 72, 90)
U_RATE = {"downs": 6, "executions": 3, "revives": 1.5, "headshots": 1.5, "marks": 5, "heals": 1, "special-executions": 1, "molotov-downs": 0.5,
          "nail-bomb-downs": 0.5, "gifts": 1, "shiv-kills": 0.3, "long-range-downs": 1, "assists": 3, "team-revenge": 0.6, "streaks-stopped": 0.25,
          "retaliations": 0.6, "rapid-kills": 0.5, "kills-while-hurt": 0.6, "last-one-standing": 0.2, "crafts": 4, "interrogations-denied": 0.3,
          "marked-target-kills": 1.5, "wins": 0.5, "matches": 1, "safes": 0.3}
U_RATE.update({k: 3 for k in U_CHAL if k.startswith("downs-")})        # downs with one gun (while it is the gun carried)
U_RATE.update({k: 1.5 for k in U_CHAL if k.startswith("exec-")})       # executions with one gun
if KELLIE:
    U_CHAL["kellie"] = ("kellie", 0, "KELLIE", "BE KELLIE", (1,) * 10, 1)
for _i, (_lb, (_aid, _ati)) in enumerate(sorted(U_ACH.items())):
    U_CHAL["ach-" + _aid] = ("ach", _i, "ACHIEVEMENT", "EARN THE ACHIEVEMENT " + _ati, (1,) * 10, 1)
U_FIXED = {"og": (1,) * 10, "kellie": (1,) * 10, "weeks": (1, 2, 3, 4, 6, 8, 10, 12, 12, 12), "rank": (2, 2, 2, 2, 2, 2, 3, 3, 4, 5),
           **{"ach-" + _aid: (1,) * 10 for _aid, _ati in U_ACH.values()},
           "survivors": (15, 20, 25, 30, 40, 50, 60, 75, 90, 110),
           # (the ISLANDER LONG COAT is one of the coolest Seraphite pieces and was too easy, 2 matches on the
           # Seraphite camp: the map vote brings a wanted map up often, 2 wins were an evening - the top items now ask for 10 / 15)
           "mapwins": (3, 3, 3, 3, 3, 5, 6, 8, 10, 15), "flawless": (1, 1, 1, 1, 1, 1, 2, 2, 3, 3), "streak": (4, 5, 5, 6, 6, 7, 8, 9, 10, 12),
           "melee-downs": (25, 25, 30, 40, 50, 60, 80, 100, 125, 150),   # (one row: KNIFE at level 1 = 25 melee downs)
           "best-downs": (5, 6, 7, 8, 9, 10, 11, 12, 14, 16), "best-executions": (3, 4, 4, 5, 5, 6, 6, 7, 8, 9), "best-revives": (3, 3, 4, 4, 5, 5, 6, 6, 7, 8),
           "best-headshots": (3, 4, 4, 5, 5, 6, 6, 7, 8, 9), "best-assists": (4, 5, 6, 6, 7, 8, 9, 10, 11, 12)}


def _ladder(rate):
    out = []
    for m in U_EFFORT:
        v = rate * m
        v = int(round(v / 50.0) * 50) if v >= 500 else int(round(v / 25.0) * 25) if v >= 100 else int(round(v / 5.0) * 5) if v >= 10 else int(round(v))
        lo = 5 if rate >= 1 else 3                          # (the floor: 5 of an everyday feat, 3 of a rare one - no "do it twice" rows)
        out.append(max(lo, v, out[-1] if out else lo))
    return tuple(out)


# the lowest level a feat may sit at, where the number alone does not say how long it takes: a win on ONE map needs that map to come up
# (about 18 matches for one), a clan week is seven matches, a win without a death is rare
U_MINLEVEL = {"mapwins": 9, "weeks": 5, "flawless": 5}
# one of something reads singular (the table keys of the ext's loc are these lines)
U_SINGULAR = {"mapwins": "WIN A MATCH ON %s", "weeks": "SURVIVE A WEEK", "flawless": "WIN A MATCH WITHOUT DYING", "safes": "CRACK A SAFE IN INTERROGATION"}


for _k in list(U_CHAL):
    assert (_k in U_RATE) != (_k in U_FIXED), _k
    U_CHAL[_k] = U_CHAL[_k][:4] + (U_FIXED[_k] if _k in U_FIXED else _ladder(U_RATE[_k]), U_MINLEVEL.get(_k, U_CHAL[_k][5]))
# per category: the themed pool, drawn in order (each faction / sex starts at another place, so the four outfits differ)
U_POOL = {
    "hat": ("headshots", "marks", "long-range-downs", "downs-hunting-rifle", "downs-semi-auto", "downs-bow", "rank", "mapwins"),
    # (the masks left HEADWEAR with the feats they carried - the eye at its sharpest)
    "mask": ("best-headshots", "exec-hunting-rifle", "marked-target-kills", "exec-bow", "mapwins", "long-range-downs", "headshots",
             "downs-hunting-rifle"),
    "torso": ("downs", "weeks", "rank", "executions", "streak", "mapwins", "survivors", "special-executions", "downs-burst-rifle", "team-revenge",
              "wins", "exec-variable-rifle", "best-downs", "kills-while-hurt", "exec-full-auto", "mapwins", "flawless", "exec-burst-rifle",
              "exec-burst-pistol", "exec-enforcer"),     # (two sidearm feats moved here from lower; rank third - the hats are easy or themed now)
    "lower": ("assists", "downs-9mm", "rapid-kills", "downs-revolver", "mapwins", "downs-shorty", "exec-shorty", "retaliations", "exec-9mm",
              "best-assists", "exec-revolver"),
    # (the bag lists are short now (the repeats are gone): four of the carrier feats moved to FACE so every feat is still on an item)
    "backpack": ("gifts", "heals", "crafts", "revives", "molotov-downs", "mapwins"),
    "face": ("executions", "survivors", "last-one-standing", "exec-semi-auto", "mapwins", "interrogations-denied", "exec-tactical-shotgun",
             "weeks", "exec-frontier-rifle", "best-executions", "mapwins", "shiv-kills", "streaks-stopped", "flawless", "rank",
             "nail-bomb-downs", "safes", "best-revives", "matches",
             "exec-9mm", "best-assists", "exec-revolver"),     # (the Seraphite trousers draw from their own pool now - these three came here)
    "melee": ("melee-downs",),
}
# the maps a map-wins challenge names: the live rotation (= daemon.MAPS / SP_MAPS image keys, t2r-ext MF_MAPS img). Not School / Gas
# Station (not in the map pool, T2R_MAP_EXCLUDE) and not the Part I maps (Bookstore / Plaza: DLC, only for owners).
# Not Chase (requirements on maps outside the pool are impossible: release/build_release.py
# SHIP_SP_MAPS has no chase, so no client offers it).
U_MAPS = (("forest", "FOREST"), ("shipyard", "SHIPYARD"), ("resort", "RESORT"), ("seraphite-camp", "SERAPHITE CAMP"), ("houses", "HOUSES"),
          ("hospital", "HOSPITAL"), ("train-station", "TRAIN STATION"), ("wilds-houses", "HILLSIDE"), ("capitol-shops", "CAPITOL HILL SHOPS"),
          ("into-the-city", "CONVENTION CENTER"), ("overpass", "OVERPASS"), ("jackson-market", "SUPERMARKET"))
U_NOLOCK = ("sex",)


_MAP_TURN = [0, {}]   # map-wins walk the map list, each category its pool, across every list (table() builds them in a fixed order: same each run)


# How striking an item is, 1 (plain) .. 5 (the one everybody wants): its unlock level (the cooler the clothes, the harder they
# should be to get: caps easy, gas masks harder, basic vests easier, cool jackets harder). By label; a label that is not
# here is class 2. Class -> level 1..10: U_COOL_LEVEL (two neighbouring levels per class, taken in turn, so one class is not one number).
U_COOL = {
    # headwear: caps are everyday, the story gas masks are the prizes
    "WLF CAP": 1, "PATROL CAP": 1, "FIELD CAP": 1, "BALL CAP": 1, "PATCH CAP": 1, "FADED CAP": 1, "HOOD UP": 1, "HOOD DOWN": 1,
    "GAS MASK": 3, "HALF MASK": 3, "HALF MASK I": 3, "HALF MASK II": 3,
    "BEANIE": 2, "SLOUCH BEANIE": 2, "WOOL BEANIE": 3, "FOLDED BEANIE": 3, "RANCHER HAT": 4, "COWBOY HAT": 4,
    "DINA'S GAS MASK": 4, "ELLIE'S GAS MASK": 4, "LEV'S GAS MASK": 4, "ABBY'S GAS MASK": 5, "BONG MASK": 5,
    # WLF tops: knitwear and vests plain, harness rigs in the middle, leather and hooded rigs on top
    "CREW SWEATER": 1, "OVERSHIRT": 1, "LIGHT JACKET": 1, "FLEECE VEST": 1, "QUILTED VEST": 1, "PUFFER VEST": 1, "HALF-ZIP PULLOVER": 1,
    "PATCH VEST": 2, "FIELD JACKET": 2, "WORK JACKET": 2, "WORN ZIP JACKET": 2, "ROLLED-SLEEVE JACKET": 2, "UTILITY JACKET": 2,
    "UTILITY VEST": 2, "OPEN JACKET": 2, "CANVAS JACKET": 2, "SOFTSHELL JACKET": 2, "HOODIE": 2,
    "HENLEY, HARNESS": 3, "LONG SLEEVE, HARNESS": 3, "THERMAL, HARNESS": 3, "M-65 JACKET": 3, "QUILTED VEST, HARNESS": 3,
    "JACKET AND HOODIE": 3, "ZIP JACKET, HARNESS": 3,
    "LEATHER JACKET": 4, "HOODED JACKET, HARNESS": 4, "SHELL JACKET, HARNESS": 4, "DARK JACKET, HARNESS": 4,
    "BLACK LEATHER JACKET": 5,
    # Seraphite tops: shirts plain, strapped coats in the middle, the elders' and the islanders' on top
    "LINEN SHIRT": 1, "STAINED SHIRT": 1, "ROLLED-SLEEVE SHIRT": 1,
    "TAN RAINCOAT": 2, "WEATHERED RAINCOAT": 2, "LEATHER RAINCOAT": 2, "WORN LEATHER RAINCOAT": 2, "RAGGED SHIRT": 2,
    "RAINCOAT, HOLSTER STRAP": 3, "RAINCOAT, MACHETE SLING": 3, "RAINCOAT, KNIFE STRAP": 3, "SHIRT, HOLSTER STRAP": 3,
    "SHIRT, MACHETE SLING": 3, "OPEN RAGGED SHIRT": 3, "ISLANDER SHIRT": 3,
    "SHIRT, KNIFE HARNESS": 4, "ELDER'S TUNIC": 4, "TORN SLEEVELESS TOP": 4, "HOODED RAINCOAT": 4,
    "TORTURED": 5, "ELDER'S HOODED COAT": 5, "ISLANDER LONG COAT": 5,
    # legs and bags
    "BROWN CARGO PANTS": 1, "KHAKI CARGO PANTS": 1, "OLIVE CARGO PANTS": 1, "BELTED CARGO PANTS": 2, "FADED CARGO PANTS": 2,
    "CARGO PANTS, DROP HOLSTER": 3, "LINEN TROUSERS": 1, "WOOL TROUSERS": 1, "FIELD TROUSERS": 2,
    "WORK TROUSERS": 2, "RAGGED TROUSERS": 3,
    "CANVAS DAYPACK": 1, "SCHOOL BAG": 1, "PATCHED RUCKSACK": 2, "FIELD PACK": 3, "TACTICAL PACK": 4, "LEATHER RUCKSACK": 2,
    "KNIFE": 1,
}
U_COOL_LEVEL = {1: (1, 2), 2: (3, 4), 3: (5, 6), 4: (7, 8), 5: (9, 10)}
# TIERS (basically cooler = harder, simpler =
# easier; similar rules for the clothing not named; not too tedious but not too easy, find a balance).
# Four tiers: 1 EASY, 2 MEDIUM, 3 HARD, 4 ELITE. U_TIER = what the file says for an item (an entry marked "(m)" there = the male list
# only: U_TIER_M); an item the file does not name takes its tier from the class above (U_TIER_OF_COOL). U_TIER_LEVEL: the levels of
# the ten-step ladder a tier takes in turn - easy 6 / 9 / 13 matches of its feat, medium 18 / 25 / 34, hard 45 / 58, elite 72 / 90.
# (OVERSHIRT (m) stands in the file under Easy and under Medium: Easy - a plain shirt.)
U_TIER = {
    # easy
    "PATROL CAP": 1, "BALL CAP": 1, "FADED CAP": 1, "SLOUCH BEANIE": 1, "GAS MASK": 1, "HALF MASK": 1, "HALF MASK I": 1, "HALF MASK II": 1,
    "QUILTED VEST": 1, "QUILTED VEST, HARNESS": 1, "FLEECE VEST": 1, "PUFFER VEST": 1, "UTILITY VEST": 1, "JACKET AND HOODIE": 1,
    "OPEN JACKET": 1, "FADED CARGO PANTS": 1,
    # medium
    "COWBOY HAT": 2, "RANCHER HAT": 2, "BEANIE": 2, "FOLDED BEANIE": 2, "WOOL BEANIE": 2, "DINA'S GAS MASK": 2, "ELLIE'S GAS MASK": 2,
    "HALF-ZIP PULLOVER": 2, "SOFTSHELL JACKET": 2, "LIGHT JACKET": 2, "KHAKI CARGO PANTS": 2,
    # hard
    "LEV'S GAS MASK": 3, "CANVAS JACKET": 3, "DARK JACKET, HARNESS": 3, "BELTED CARGO PANTS": 3, "ELDER'S TUNIC": 3, "ISLANDER SHIRT": 3,
    "HOODED RAINCOAT": 3,
    # elite
    "ABBY'S GAS MASK": 4, "FIELD JACKET": 4, "M-65 JACKET": 4, "ISLANDER LONG COAT": 4, "TORN SLEEVELESS TOP": 4, "TORTURED": 4,
    "ELDER'S HOODED COAT": 4,
}
U_TIER_M = {
    "WLF CAP": 1, "PATROL CAP": 1, "FIELD CAP": 1, "BALL CAP": 1, "CREW SWEATER": 1, "FIELD JACKET": 1, "PATCH VEST": 1,
    "ROLLED-SLEEVE JACKET": 1, "OVERSHIRT": 1, "HENLEY, HARNESS": 1, "WORN ZIP JACKET": 1, "LONG SLEEVE, HARNESS": 1, "UTILITY JACKET": 1,
    "THERMAL, HARNESS": 1,
    "LEATHER JACKET": 2, "BLACK LEATHER JACKET": 2,
    "WORK JACKET": 4,
}
U_TIER_OF_COOL = {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}
U_TIER_LEVEL = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8), 4: (9, 10)}


def unlock_tier(sex, label):
    if sex == "m" and label in U_TIER_M:
        return U_TIER_M[label]
    return U_TIER.get(label, U_TIER_OF_COOL[U_COOL.get(label, 2)])


# THEMES (same file: "keep stuff thematic like cowboy hats needing western weapons, seraphite clothes needing seraphite weaponry
# (islander long coat for bow kills maybe)"; "Cowboy Hat (make frontier rifle related)", "Rancher Hat (make revolver related)").
# U_PIN: an item asks for exactly this feat (its tier still picks the number). U_POOL_FAC: the Seraphite tops draw from the
# Seraphites' own kit - bow, hunting rifle, the knife in the dark, the clan - instead of the WLF's rifles and pistols.
U_PIN = {
    "COWBOY HAT": "exec-frontier-rifle", "RANCHER HAT": "downs-revolver",
    "ISLANDER LONG COAT": "downs-bow", "ISLANDER SHIRT": "exec-bow", "ELDER'S TUNIC": "downs-hunting-rifle",
    "ELDER'S HOODED COAT": "exec-hunting-rifle", "TORTURED": "interrogations-denied", "TORN SLEEVELESS TOP": "kills-while-hurt",
    # the story masks by whose they are: Lev's bow, Ellie's switchblade, Abby's fists, Dina at your side
    "LEV'S GAS MASK": "downs-bow", "ELLIE'S GAS MASK": "shiv-kills", "ABBY'S GAS MASK": "special-executions", "DINA'S GAS MASK": "revives",
    "HOODED JACKET, HARNESS": "rank",                    # VETERAN (the M-65 JACKET had it; that one is an achievement's now)
    "WORK JACKET": "flawless",                           # (elite on the male list: UNTOUCHED)
}
U_POOL_FAC = {
    ("scar", "torso"): ("shiv-kills", "downs-bow", "weeks", "long-range-downs", "special-executions", "exec-bow", "survivors", "streak",
                        "downs-hunting-rifle", "last-one-standing", "exec-hunting-rifle", "mapwins", "flawless"),
    ("scar", "hat"): ("downs-bow", "shiv-kills", "long-range-downs"),
    ("scar", "lower"): ("shiv-kills", "exec-bow", "retaliations", "downs-hunting-rifle", "assists"),
}
# rows outside the ladder (the bong mask is an og role exclusive (anyone who played before public release has
# it unlocked); the requirement has no progress bar and says FOR MY FELLOW STONERS THAT HELPED SHAPE THIS MOD): label -> feat
U_EXCLUSIVE = {"BONG MASK": "og", **{_lb: "ach-" + _aid for _lb, (_aid, _ati) in U_ACH.items()}}
if KELLIE:
    U_EXCLUSIVE.update({_r["label"]: "kellie" for _r in KELLIE["rows"]})


# A row taken out of a list after release moves the ladder: every later row of that list (and the lists after it, which go on
# with the pool's turn) would get another challenge, and an item a player had unlocked could lock again. LADDER_GHOST keeps the
# ladder as it was: (faction, sex) -> {category: (label, index, tier)} = the removed row, which was that list's default. The ladder
# runs as if it still stood there as the default; the new default takes its old place on the ladder and is then made free.
# (Tan Raincoat of the male Seraphites was removed and Weathered Raincoat made the default instead)
LADDER_GHOST = {("scar", "m"): {"torso": ("TAN RAINCOAT", 0, 1)}}


def assign_unlocks(key, T):
    d = DEFAULTS[key]
    home = [0]                                              # this outfit has its map-win item
    for c in CATS:
        items = T[c]
        dflt = d.get(c, 0)
        real = None
        g = LADDER_GHOST.get(key, {}).get(c)
        if g:
            real = items[dflt]
            items = items[:g[1]] + [dict(label=g[0], tier=g[2])] + items[g[1]:]
            dflt = g[1]
        # the items wearable in MP today (tier 1) take the easy end of the ladder: the first unlocks are ones the player can put on
        rest = sorted((k for k in range(len(items)) if k != dflt and items[k]["label"] != "NONE" and items[k]["label"] not in U_EXCLUSIVE),
                      key=lambda k: (items[k]["tier"], k))   # (bare head: never a reward)
        turn = {}
        for it in items:
            it["unlock"] = None
        if c in U_NOLOCK:
            continue
        pool = U_POOL_FAC.get((key[0], c), U_POOL[c])
        tk = c if pool is U_POOL[c] else key[0] + " " + c
        cur = _MAP_TURN[1].get(tk, 0)                   # (each outfit goes on where the one before stopped: every feat gets used)
        m = len(rest)
        for j, k in enumerate(rest):
            if c == "face":                                 # faces: nobody's is cooler - an even, mild climb through the list
                lvl = 1 + (round(j * 6 / (m - 1)) if m > 1 else 0)
            else:
                cl = unlock_tier(key[1], items[k]["label"])
                lvl = U_TIER_LEVEL[cl][turn.get(cl, 0) % len(U_TIER_LEVEL[cl])]
                turn[cl] = turn.get(cl, 0) + 1
            pin = U_PIN.get(items[k]["label"])
            if pin:                                         # the item's own feat, at the item's level (never under the feat's floor)
                ch, lvl = pin, max(lvl, U_CHAL[pin][5])
            elif "mapwins" in pool and lvl >= U_CHAL["mapwins"][5] and not home[0]:
                # the map win sits only on the top items (its level floor), and the pool's turn reached it there by luck alone (three
                # more wearable rows moved the turn and no item of the game carried it) -> the first top item of an outfit takes it
                ch, home[0] = "mapwins", 1
            else:
                for t in range(len(pool)):                  # the next challenge of the pool that may sit this low
                    ch = pool[(cur + t) % len(pool)]
                    if U_CHAL[ch][5] <= lvl and not (ch == "mapwins" and home[0]):
                        cur = (cur + t + 1) % len(pool)
                        break
            n = U_CHAL[ch][4][lvl - 1]
            mp = 0
            if ch == "mapwins":
                mp = _MAP_TURN[0] % len(U_MAPS)
                _MAP_TURN[0] += 1
            items[k]["unlock"] = (ch, n, mp)
        for it in items:
            if it["label"] in U_EXCLUSIVE:
                it["unlock"] = (U_EXCLUSIVE[it["label"]], 1, 0)
        if real is not None:
            real["unlock"] = None                           # (the new default: free, its old ladder place stays used)
        _MAP_TURN[1][tk] = cur


def unlock_title(u):
    return U_CHAL[u[0]][2]


def unlock_text(u):
    """= customize.c cz_lock_text (without the title and the progress)."""
    ch, n, mp = u
    line = U_CHAL[ch][3]
    if "%" not in line:
        return line
    if n == 1 and ch in U_SINGULAR:
        line = U_SINGULAR[ch]
        return line % U_MAPS[mp][1] if "%s" in line else line
    return line % ((n, U_MAPS[mp][1]) if "%s" in line else n)


# The look each (faction, sex) starts from: the first pool look (dc_data_patches FACTION_LOOKS / FEMALE_LOOKS), by label so a list
# edit keeps it. WLF male: militia-male-11's own head has a bandana (HAT_HEADS), so the default face is head 14.
DEFAULT_LABELS = {("wlf", "m"): {"hat": "NONE", "torso": "HOODIE", "lower": "CARGO PANTS, DROP HOLSTER", "backpack": "CANVAS DAYPACK", "face": "FACE 14"},
                  ("wlf", "f"): {"hat": "BALL CAP", "torso": "QUILTED VEST", "lower": "CARGO PANTS, DROP HOLSTER", "backpack": "SCHOOL BAG", "face": "FACE 13"},
                  ("scar", "m"): {"hat": "HOOD DOWN", "torso": "WEATHERED RAINCOAT", "lower": "LINEN TROUSERS", "backpack": "LEATHER RUCKSACK", "face": "FACE 13"},
                  ("scar", "f"): {"hat": "HOOD DOWN", "torso": "WORN LEATHER RAINCOAT", "lower": "WOOL TROUSERS", "backpack": "LEATHER RUCKSACK", "face": "FACE 11"}}


def _defaults():
    out = {}
    for (fac, sex), want in DEFAULT_LABELS.items():
        T = _wlf(sex) if fac == "wlf" else _scar(sex)
        held = HELD.get((fac, sex), ())                  # (the lists as table() makes them: a held row before the default shifts its index)
        out[(fac, sex)] = {c: [it["label"] for it in T[c] if it["label"] not in held].index(lb) for c, lb in want.items()}
    return out


DEFAULTS = _defaults()


def table_id():
    """= customize_core.h cz_table_id(): FNV-1a over every label, list by list (MSG_CUSTOM_LOOK carries it)."""
    T = table()
    h = 2166136261
    for fac in FACTIONS:
        for sex in SEXES:
            for c in CATS:
                for it in T[(fac, sex)][c]:
                    for ch in it["label"].encode("utf-8"):
                        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
                    h = ((h ^ 0x1f) * 16777619) & 0xFFFFFFFF
                h = ((h ^ 0x1e) * 16777619) & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


def cstr(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def header():
    """tools/ext/customize_items.h: labels, tiers and parts per (faction, sex, category)."""
    T = table()
    L = ["// GENERATED by tools/features/customize_items.py --header. Do not edit; edit the .py and re-run.",
         "// Indexes are saved + sent (MSG_CUSTOM_LOOK): the lists are append-only.",
         "#pragma once", "#define CZ_NFAC 2", "#define CZ_NSEX 2", "#define CZ_NCAT %d" % len(CATS),
         "typedef struct { const char *label; unsigned char tier; const char *const *parts; const char *const *props; "
         "const char *const *hide; unsigned char uk, um; unsigned short un; const char *pic; unsigned char hid; } cz_item_t;     // uk: CZ_CHAL index (0 = free), un: the number, um: CZ_UMAP index (map wins), pic: card picture (icons/<pic>.png) or NULL, hid: listed for its owner only",
         "typedef struct { int n; const cz_item_t *items; } cz_list_t;"]
    for i, c in enumerate(CATS):
        L.append("#define CZ_%s %d" % (c.upper(), i))
    L.append("static const char *const CZ_CAT_LABEL[CZ_NCAT] = {%s};" % ", ".join(cstr(CAT_LABEL[c]) for c in CATS))
    for i, k in enumerate(U_KINDS):
        L.append("#define CZK_%s %d" % (k.upper(), i + 1))
    L.append("#define CZK_N %d" % (len(U_KINDS) + 1))
    L.append("static const char *const CZK_KEY[CZK_N] = {\"\", %s};" % ", ".join(cstr(k) for k in U_KINDS))
    L.append("#define CZ_NLBL 64          // per-match counters (t2r-ext.c g_mis_cnt, MIS_N): file key per counted id, NULL = not kept")
    L.append("static const char *const CZ_LBL_KEY[CZ_NLBL] = {%s};" % ", ".join(cstr(U_LABELS[i]) if i in U_LABELS else "NULL" for i in range(64)))
    L.append("typedef struct { unsigned char kind, arg; const char *key, *title, *line; } cz_chal_t;   // kind CZK_*, arg = counter id (count / best)")
    L.append("#define CZ_NCHAL %d" % (len(U_CHAL) + 1))
    L.append("static const cz_chal_t CZ_CHAL[CZ_NCHAL] = {{0, 0, \"\", \"\", \"\"},")
    for ch, (kind, arg, title, line, _lv, _lo) in U_CHAL.items():
        L.append("    {CZK_%s, %d, %s, %s, %s}," % (kind.upper(), arg, cstr(ch), cstr(title), cstr(line.replace("%d", "%u"))))
    L.append("};")
    L.append("#define CZ_NUMAP %d" % len(U_MAPS))
    L.append("static const char *const CZ_UMAP_KEY[CZ_NUMAP] = {%s};" % ", ".join(cstr(k) for k, _ in U_MAPS))
    L.append("static const char *const CZ_UMAP_NAME[CZ_NUMAP] = {%s};" % ", ".join(cstr(n) for _, n in U_MAPS))
    nid = 0
    lists = {}
    for (fac, sex), cats in T.items():
        for c in CATS:
            rows = []
            for it in cats[c]:
                arrs = []
                for key in ("parts", "props", "hide"):
                    if it[key]:
                        nm = "cz_s%d" % nid
                        nid += 1
                        L.append("static const char *const %s[] = {%s, NULL};" % (nm, ", ".join(cstr(x) for x in it[key])))
                        arrs.append(nm)
                    else:
                        arrs.append("NULL")
                u = it.get("unlock")
                uk, un, um = (list(U_CHAL).index(u[0]) + 1, u[1], u[2]) if u else (0, 0, 0)
                pic = card_pic(c, it)
                rows.append("{%s, %d, %s, %d, %d, %d, %s, %d}" % (cstr(it["label"]), it["tier"], ", ".join(arrs), uk, um, un, cstr(pic) if pic else "NULL",
                                                                  it.get("hid", 0)))
            nm = "cz_l_%s_%s_%s" % (fac, sex, c)
            L.append("static const cz_item_t %s[] = {\n    %s};" % (nm, ",\n    ".join(rows)))
            lists[(fac, sex, c)] = (nm, len(rows))
    L.append("static const cz_list_t CZ_LISTS[CZ_NFAC][CZ_NSEX][CZ_NCAT] = {")
    for fac in FACTIONS:
        L.append("  {")
        for sex in SEXES:
            L.append("    {" + ", ".join("{%d, %s}" % (lists[(fac, sex, c)][1], lists[(fac, sex, c)][0]) for c in CATS) + "},")
        L.append("  },")
    L.append("};")
    L.append("static const unsigned char CZ_DEFAULT[CZ_NFAC][CZ_NSEX][CZ_NCAT] = {")
    for fac in FACTIONS:
        L.append("  {" + ", ".join("{" + ", ".join(str(DEFAULTS[(fac, sex)].get(c, 0)) for c in CATS) + "}" for sex in SEXES) + "},")
    L.append("};")
    if HANDTINT:        # the WLF outfit record of a face: "<body record>-<CZ_WLF_TONE[sex][face]>" (customize_looks.py; wlf_tones above)
        tones = {sex: wlf_tones(sex)[0] for sex in SEXES}
        n = max(len(v) for v in tones.values())
        L.append("// WLF skin tone group per face (the hand tint's outfit records are per tone group, not per face: the level def's 512 symbols)")
        L.append("#define CZ_WLF_TONES %d" % n)
        L.append("static const unsigned char CZ_WLF_TONE[CZ_NSEX][CZ_WLF_TONES] = {")
        for sex in SEXES:
            L.append("  {" + ", ".join(str(g) for g in tones[sex] + [0] * (n - len(tones[sex]))) + "},")
        L.append("};")
    return "\n".join(L) + "\n"


# WLF SKIN TONE GROUPS (build #18 did not boot: "Too many modules in level starlight-mp-test [Max 512]" - the engine's
# level def takes at most 512 `symbol` lines (LevelDef::ReadTxtFile, ParseInfo::AddModule) and the WLF outfit records per FACE
# (9 bodies x 23 faces = 207 symbols, for the hand tint) brought the level to 560). Faces of one skin tone now share their outfit
# records: a WLF face's record is "<body record>-<tone group>" (customize_looks.face_name), the group from wlf_tones():
# greedy in list order (the lists are append-only, so a face keeps its group), a face joins the first group whose mean colour is
# within WLF_TONE_TOL per channel of its own (0.045: 3 male + 6 female groups, worst error 0.042 - under the calibration's own
# residual, tools/models/wlf_face_tint.py). 9 x 9 = 81 records instead of 207.
WLF_TONE_TOL = 0.045


def wlf_face_colour(sex, it):
    """the palette colour of a WLF list face (data/wlf_face_tint.json): its kit's head; KELLIE (a head built from kit 10) = 10's"""
    cols = HANDTINT["colours"][sex]
    hd = it["parts"][0] if it["parts"] else ""
    kk = hd.split("-head-")[1][:2] if "-head-" in hd and not hd.startswith("t2r-kl-") else "10"
    return cols.get(kk, cols.get("10", [0.85, 0.78, 0.76])), kk in cols


def wlf_tones(sex):
    """-> (group index per face of the WLF list of that sex, [rgb per group], [labels without a colour of their own]); HANDTINT only"""
    faces = table()[("wlf", sex)]["face"]
    cols, miss, groups = [], [], []
    for it in faces:
        c, own = wlf_face_colour(sex, it)
        cols.append(c)
        if not own:
            miss.append(it["label"])
    of = []
    for i, c in enumerate(cols):
        for g, mem in enumerate(groups):
            mean = [sum(cols[j][ch] for j in mem) / len(mem) for ch in range(3)]
            if max(abs(mean[ch] - c[ch]) for ch in range(3)) <= WLF_TONE_TOL:
                mem.append(i)
                of.append(g)
                break
        else:
            groups.append([i])
            of.append(len(groups) - 1)
    rgb = [[round(sum(cols[j][ch] for j in mem) / len(mem), 3) for ch in range(3)] for mem in groups]
    return of, rgb, miss


def ach_header():
    """tools/ext/customize_ach.h: which achievement opens which item (U_ACH) - read by customize.c (the grant once it is earned) and
    by the achievements page / unlock card for their "UNLOCKS: <label>" line. Rows in the order of U_CHAL's ach-* entries."""
    L = ["#pragma once     // (achieve_ui.c and customize.c both include it in the one translation unit)",
         "// generated by tools/features/customize_items.py --header (U_ACH) - do not edit",
         "// achievement id (tools/achievements.py) -> the CUSTOMIZE item it unlocks (the item's list label, a loc key)",
         "static const struct { const char *ach, *label; } CZ_ACH_UNLOCKS[] = {"]
    for lb, (aid, _ti) in sorted(U_ACH.items()):
        L.append('    {"%s", "%s"},' % (aid, lb))
    L += ["    {0, 0}", "};", "#define CZ_ACH_NUNLOCKS %d" % len(U_ACH)]
    return "\n".join(L) + "\n"


def main():
    T = table()
    if "--header" in sys.argv:
        out = os.path.join(ROOT, "tools", "ext", "customize_items.h")
        open(out, "w", newline="\n").write(header())
        print("wrote", out)
        open(os.path.join(ROOT, "tools", "ext", "customize_ach.h"), "w", newline="\n").write(ach_header())
        return
    for (fac, sex), cats in T.items():
        print("== %s %s" % (FAC_LABEL[fac], "MALE" if sex == "m" else "FEMALE"))
        for c in CATS:
            print("  %-9s %2d:" % (c, len(cats[c])))
            for it in cats[c]:
                print("      %-26s tier %d  %s" % (it["label"], it["tier"], "%s: %s" % (unlock_title(it["unlock"]), unlock_text(it["unlock"])) if it.get("unlock") else "FREE (default)"))


if __name__ == "__main__":
    main()
