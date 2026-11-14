"""The layer table of the execution sound design plus.

Shared by tools/rip_t2_execplus.py (rips / mixes the waves: execplus.pcm + execplus.h) and re/factions2013/t1anim/gen_execplus.py (the per-move timing
table: execplus_tl.h). The ORDER is the C enum (EPL_*). A layer is one KIND of sound; a row of the timeline says when, on which body / joint, how loud.

  name   enum name without EPL_
  prio   mixer priority: 0 = keeps its voice always (falls, grabs), 1 = dropped when the mixer is 3/4 full, 2 = first to go (gear, cloth, blood, thumps)
  base   per-layer gain in percent of the lead level (the lead hits play at t2r-melee-sfx-gain = 0.45; a layer at base 50 and row gain 255 is ~half of that)
  src    'pcm' ripped waves (execplus.pcm) | 'fs0' 'fs1' 'fs2' the footsteps.pcm tiers (sprint / run / walk, no new data) | 'vox' a voice event (no wave)
  gap    min ms between two plays of the layer on the SAME body in one move (the density limiter; the generator keeps rows apart too)
"""

LAYERS = [
    # name,           prio, base, src,   gap
    ("STEP_L",         1,   55, "fs2",  140),     # walking / shuffling step planting
    ("STEP_M",         1,   62, "fs1",  120),     # a firm run-in / turn step
    ("STEP_H",         1,   68, "fs0",  120),     # a hard stamp / sprint plant / landing
    ("STEP_SWEET",     2,   45, "pcm",  100),     # chucks heel + toe sweetener under every step
    ("SCUFF",          1,   50, "pcm",  160),     # sole dragging / sliding on the ground
    ("PIVOT",          2,   45, "pcm",  300),     # a weight shift / turn on the spot (shoe twist + cloth)
    ("WH_ARM_S",       1,   50, "pcm",  140),     # arm swing whooshes, by speed
    ("WH_ARM_M",       1,   58, "pcm",  140),
    ("WH_ARM_L",       1,   66, "pcm",  140),
    ("WH_LEG",         1,   62, "pcm",  180),     # leg swing (knee / kick)
    ("WH_BODY",        2,   48, "pcm",  200),     # torso lunge / throw / duck: cloth swish
    ("WH_GUN",         1,   55, "pcm",  200),     # a gun swung / raised: movement foley + air
    ("CL_S",           2,   38, "pcm",  120),     # cloth rustle, 2 materials (0 cotton / parka = Seraphites, 1 leather / military = WLF)
    ("CL_M",           2,   44, "pcm",  140),
    ("CL_L",           2,   52, "pcm",  180),
    ("GR_TORSO",       0,   55, "pcm",  200),     # hands taking hold of cloth on a torso
    ("GR_ARM",         0,   50, "pcm",  200),     # ... an arm / wrist / shoulder
    ("GR_HEAD",        0,   52, "pcm",  200),     # ... head / hair / face / neck
    ("GR_RELEASE",     1,   40, "pcm",  200),     # letting go: skin + cloth swipe
    ("STRUG_TORSO",    1,   42, "pcm",  380),     # a held body fighting the grip
    ("STRUG_HEAD",     1,   42, "pcm",  380),
    ("FALL_BODY_M",    0,   60, "pcm",  200),     # a body hitting the floor (medium / heavy), cloth + thud
    ("FALL_BODY_H",    0,   68, "pcm",  200),
    ("FALL_HEAD",      0,   56, "pcm",  200),     # a head landing: skull + hair
    ("FALL_KNEE",      0,   54, "pcm",  200),     # knee(s) on the ground: trouser + sole
    ("FALL_HAND",      1,   46, "pcm",  200),     # a bracing hand / forearm slap
    ("HIT_BODY",      1,   52, "pcm",  160),     # a knee / shoulder / foot landing on the victim's clothed body (not a punch: the lead hits stay)
    ("SLIDE",          1,   44, "pcm",  500),     # body dragged / sliding on the ground
    ("THUMP",          2,   40, "pcm",  250),     # low-end body-weight layer under heavy falls / weapon kills (not under punches)
    ("BONE",           2,   36, "pcm",  250),     # dry bone crack sweetener under heavy weapon / kill blows (not under punches)
    ("GEAR_PACK",      2,   30, "pcm",  300),     # backpack / pouches shifting
    ("GEAR_STRAP",     2,   32, "pcm",  300),     # long-gun sling
    ("GEAR_HOLSTER",   2,   28, "pcm",  350),     # holster leather creak
    ("GEAR_MELEE",     2,   30, "pcm",  350),     # a melee weapon on the belt / back
    ("WPN_GRIP_PISTOL", 1,  48, "pcm",  400),     # re-gripping a pistol
    ("WPN_GRIP_LONG",  1,   48, "pcm",  400),     # re-gripping a long gun
    ("WPN_LOWER_PISTOL", 1, 44, "pcm",  400),     # gun comes down after the shot
    ("WPN_LOWER_LONG", 1,   44, "pcm",  400),
    ("BLOOD_SPLAT",    2,   26, "pcm",  250),     # wet splash on the ground
    ("BLOOD_DRIP",     2,   22, "pcm",  350),
    # voice events (the `say` call, a female speaker gets her own take through fem_effort_sid); the lists are in t2r-ext.c
    ("VOX_ATT_BREATH", 1,  100, "vox",  700),     # the executioner's fight breathing
    ("VOX_ATT_EFFORT", 1,  100, "vox",  700),     # the executioner's strain (grip, haul)
    ("VOX_ATT_RELIEF", 1,  100, "vox",  900),     # the exhale after the kill
    ("VOX_VIC_PAIN",   1,  100, "vox",  700),     # victim takes a blow
    ("VOX_VIC_STRUGGLE", 1, 100, "vox", 700),     # victim fights the hold
    ("VOX_VIC_CHOKE",  1,  100, "vox",  900),     # cough / gurgle / choke
    ("VOX_VIC_FALL",   1,  100, "vox",  900),     # the knock-out-of-the-lungs groan on landing
    ("VOX_VIC_WHIMPER", 1, 100, "vox",  900),
]
NAMES = [l[0] for l in LAYERS]
IDX = {n: i for i, n in enumerate(NAMES)}

# joint codes of a row (where the sound sits; the ext asks the engine for that joint's world position, falling back to the body)
JOINTS = ["ROOT", "HEAD", "SPINE", "PELVIS", "L_HAND", "R_HAND", "L_FOOT", "R_FOOT", "L_KNEE", "R_KNEE", "WEAPON"]
JIDX = {n: i for i, n in enumerate(JOINTS)}

# where the loudest moment of a whoosh wave sits inside it (ms; the ripper aligns every variant so, the generator schedules the row that much ahead of the speed peak)
PEAK_MS = {"WH_ARM_S": 100, "WH_ARM_M": 150, "WH_ARM_L": 170, "WH_LEG": 150, "WH_BODY": 150, "WH_GUN": 140}
