"""More team voice lines (the same few lines were heard constantly in v1.08).

How a team line plays (re/vox-lines.md): winmm FUN_18004b800(kind, slot, line) runs the DC native `say`
("player" or the speaker's puppet, line) and sends msg 10 [slot][line] to the teammates; `say` resolves the
line id to a `vox-info` record in the mod's DC module vox-igc-greenlight.bin (re/modfs: 126 vox-igc-to1-* records), whose +0x70 field is the SPEECH key (fnv64 of a stream name in
speech1/english.xvag-index.json, streamed from speech1/<language>.psarc - no sound bank involved: the stock
records already play SP-only lines like scrmd-gam-fob-* in MP).

This tool adds records for the TLOU2 human enemy barks of the four WLF voices (mltma/b/c/d = vox-militia-male-a..d)
and the four Seraphite voices (scrma..scrmd), picked per KIND (2013 Factions vox-mp events, re/t1ps3
dc1/vox-mp.dci), so every player has his own voice (the look -> a..d, t2r-ext VOX_LOOK_LETTER) and every event
a pool of lines.

  python vox_lines.py gen     # (dev, needs the game + re/gamebin) -> data/vox_lines.json + ../ext/vox_lines.h
  build: dc_data_patches.patch_vox_lines(greenlight.bin, modules.bin) adds the records of data/vox_lines.json

A line id is t2r-vox-<voice>-<kind>-<NN> (voice = mltma..mltmd / scrma..scrmd); the same NN of one faction
and kind is the same scripted line in all four voices (only the actor differs), so the receiver can swap the
voice letter for the look it shows and the faction by kind + relative index (t2r-ext vx_remap).
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(HERE, "data", "vox_lines.json")
HEADER = os.path.join(ROOT, "tools", "ext", "vox_lines.h")
GAME = os.environ.get("T2_GAME", "C:/Games/T2R-A")
GAMEBIN = os.environ.get("T2R_GAMEBIN", os.path.join(ROOT, "re", "gamebin"))
FACTIONS = ("scr", "mlt")            # t2r-ext faction index: 0 Seraphites, 1 WLF (fl_hud_team / fl_pool)
VOICES = "abcd"

# kinds: the order is the t2r-ext VX_* enum (vox_lines.h). (name, what triggers it - see t2r-ext vx_event)
KINDS = [
    ("intro", "match start, first speaker of the team (2013 net-match-start-call)"),
    ("mark", "we marked an enemy (winmm kind 1; 2013 coop-player-spots-enemy)"),
    ("heal", "we finished healing (winmm kind 2; 2013 player-started-healing)"),
    ("kill", "our kill / execution (winmm kind 3; 2013 net-player-net-kill-any / net-executed-player)"),
    ("down", "we downed an enemy (award Downed Enemy; 2013 net-kill-any)"),
    ("downed", "we went down (2013 coop-player-knocked-down)"),
    ("revive", "we start reviving a teammate (2013 coop-player-revive-ally-start-call)"),
    ("thanks", "a teammate revived us (2013 coop-player-revive-ally-end-rspns)"),
    ("allydown", "a teammate went down (2013 knocked-down, heard from the buddy)"),
    ("last", "our last standing teammate died (2013 net-player-overwhelmed)"),
    ("introrsp", "match start, the second teammate answers (2013 net-match-start-rspns)"),
    ("allyexecno", "a teammate near us was executed: 'No!'"),
    ("allyexecnamem", "a teammate near us was executed: his name shouted (male name pool, index = name)"),
    ("allyexecnamef", "a teammate near us was executed: her name shouted (female name pool, index = name)"),
    ("bomb", "we marked an enemy's placed bomb (the enemies' warn-ally barks)"),
    ("reload", "we reload an empty gun with a teammate near (10-14 immersion; TLOU2 enemies' 'Cover me!' / 'Watch my back!')"),
    ("noammo", "our gun is dry and the reserve is empty (10-14; the same two barks, more urgent cooldown)"),
    ("throwwarn", "an enemy throws a molotov / nail bomb in view (10-14; the enemies' see-molotov warn-ally barks)"),
    ("xstmt", "match-start exchange, speaker 1: the statement / order (EXCHANGES, line n = pair n)"),
    ("xrply", "match-start exchange, speaker 2: the reply that fits statement n"),
    ("xcomm", "match-start exchange, speaker 3: a generic comment after a small pause"),
    ("allykillmt", "a teammate (male) died by an enemy kill, killer not female: '<Name>! They got him!' tail"),
    ("allykillms", "a teammate (male) died by a female killer: '<Name>! She got him!' tail"),
    ("allykillft", "a teammate (female) died by an enemy kill, killer not female: '<Name>! They got her!' tail"),
    ("allykillfs", "a teammate (female) died by a female killer: '<Name>! She got her!' tail"),
    ("throwmolo", "WE throw a molotov in a fight (TLOU2's attack-order barks: 'Light 'em up!' / 'Purge them!')"),
    ("throwbomb", "WE throw a pipe / nail bomb in a fight (the attack-order barks: 'Take them out!' / 'Wipe them out!')"),
    ("throwsmoke", "WE throw a smoke / stun bomb in a fight (the advance orders: 'Move in!' / 'Push in!')"),
    ("smokewarn", "an enemy throws a smoke bomb at us (the enemies' own see-smoke-bmb warn barks: 'Smoke, watch it!')"),
    ("fewleft", "few enemies remaining: the enemy team has no reinforcements and 1-2 of them stand (2013 vox-event-net-few-enemies-remaining)"),
    ("matchwon", "our team won: the end-of-match banner (2013 vox-event-net-match-won)"),
    ("rapid", "we downed / killed 2+ enemies within 6 s (2013 vox-event-special-kill-rapid-kill)"),
    ("xbpull", "WE start pulling a crossbow bolt out of our own body: the horrified 'Oh jesus... oh god...' murmurs (TLOU2's mtshld-grbbed-scared lines)"),
]
EXCH_KINDS = ("xstmt", "xrply", "xcomm")
# ---------------------------------------------------------------------------------------------------------------- match-start exchanges
# The intro voice lines are a real exchange - "1 says something. 2 replies. small break. 3 says a generic comment." - instead of
# independent random lines. Round 2: the STATEMENTS are the lines winmm's intro table
# (VOX_TAB[0], winmm 0xa7660 Seraphites / 0xa76a0 WLF, the vox-igc-to1-*-intro-NNN records) played, the replies are real faction lines that
# answer them (the scripted TLOU2 conversations they come from where the next line fits, else the faction's own wry / frustrated / prayer
# responses), the comments of the third speaker are other characterful lines. Every entry is a speech stream key of ONE voice (texts are
# read from the game data); the other voices / the female voices get the stream with the SAME subtitle text in their own voice (scripted
# lines are numbered differently per actor), else the nearest voice of that gender.
# PAIRS[faction] = [(statement stream, reply stream)] - the SAME number per faction (t2r-ext maps a line across factions / genders by index);
# COMMENTS[faction] = streams for the optional third speaker (never the words of a statement or reply).
PAIRS = {
    "mlt": [
        ("mltma-gam-flo-search-aware-convo-1-sp-003", "mltma-gam-flo-search-aware-convo-1-sp-004"),        # We only got a couple of trespassers. Stay focused. / You heard what these guys have done.
        ("mltma-gam-flo-search-aware-convo-2-sp-003", "mltma-gam-flo-search-aware-convo-2-sp-004"),        # Just keep an eye out. Might be an ambush. / Fuck... this isn't how I thought today would go.
        ("mltma-gam-flo-search-aware-convo-2-sp-003", "mltma-gen-enmy-rspns-reluctant-1x-sp-003"),         # Just keep an eye out. Might be an ambush. / Got a bad feeling.
        ("mltma-gam-flo-search-unaware-convo-2-sp-004", "mltma-gam-flo-search-unaware-convo-2-sp-003"),    # They should be happy... they'll all get to reunite with their dear prophet. / Not for much longer.
        ("mltma-gam-nor-hospital-search-aware-convo-1-sp-002", "mltma-gam-nor-hospital-search-aware-convo-1-sp-003"),   # After that shit in Hillcrest, I wouldn't take them lightly. / Man if I was there--
        ("mltma-gam-res-neighborhood-house-to-ruins-enemy-convo-1-sp-006", "mltma-gam-res-neighborhood-house-to-ruins-enemy-convo-1-sp-007"),   # Think these trespassers might be working with them. / Don't drop your guard.
        ("mltma-gam-res-search-convo-1-sp-004", "mltma-gam-res-search-convo-1-sp-005"),                    # Wonder if they're related to this trespasser? / I hope there's not more of them.
        ("mltma-gam-watchtower-escape-lobby-spj-001", "mltma-gen-enmy-rspns-frstrtd-1x-sp-006"),           # Find these primitive fucks. Any Scar still here, I want them dead. / Rather just fuckin' torch this place.
        ("mltma-gam-res-search-convo-3-slf-007", "mltma-gam-res-search-convo-3-slf-008"),                  # Fuck scars... / Fuck trespassers.
        ("mltma-gam-flo-search-aware-convo-1-sp-003", "mltma-gen-enmy-rspns-reluctant-1x-sp-004"),         # We only got a couple of trespassers. Stay focused. / This doesn't feel right.
        ("mltma-gam-res-neighborhood-fight-houses-search-start-sp-001", "mltma-gen-enmy-rspns-wry-1x-sp-001"),   # Search the entire neighborhood. / Sure. I didn't have plans this weekend.
        ("mltma-gam-res-neighborhood-fight-houses-search-start-sp-001", "mltma-gen-enmy-rspns-wry-1x-sp-006"),   # Search the entire neighborhood. / Sure, why not? I've lived a full life.
    ],
    "scr": [
        ("scrmd-gam-fob-hostile-territory-sniper-intro-sp-001", "scrmd-gam-fob-hostile-territory-sniper-intro-sp-002"),   # {Name.} Come with me. You two, take the other side. / May she protect us all.
        ("scrmd-gam-fob-hostile-territory-sniper-intro-sp-001", "scrma-gam-flo-search-aware-convo-4-sp-003"),   # ... take the other side. / {breath} I'll stay vigilant.
        ("scrmd-gam-fob-hostile-territory-sniper-intro-sp-002", "scrma-gam-nor-search-unaware-convo-1-sp-004"), # May she protect us all. / ...May she guide us home.
        ("scrmd-gam-fob-hostile-territory-sniper-intro-sp-002", "scrma-gam-sle-search-unaware-convo-1-sp-003"), # May she protect us all. / May she shield us.
        ("scrmd-gam-fob-on-foot-trains-search-aware-convo-1-sp-001", "scrmd-gam-fob-on-foot-trains-search-aware-convo-1-sp-002"),   # These Wolves are capable. Be cautious. / May she protect us.
        ("scrmd-gam-fob-on-foot-trains-search-aware-convo-1-sp-001", "scrma-gam-fob-hostile-territory-search-aware-convo-2-sp-002"),  # These Wolves are capable. Be cautious. / They are one and we are many. They won't escape.
        ("scrmd-gam-fob-on-foot-trains-search-aware-convo-1-sp-001", "scrma-gam-nor-search-aware-convo-2-sp-003"),   # These Wolves are capable. Be cautious. / That's why they can't defeat us... we're not afraid of death.
        ("scrmd-gam-fob-on-foot-trains-search-aware-convo-1-sp-002", "scrma-gam-nor-search-unaware-convo-1-sp-002"),   # May she protect us. / ...May her love bring forth a better world.
        ("scrmd-gam-fob-on-foot-trains-search-aware-convo-1-sp-002", "scrma-gam-fob-on-foot-trains-search-unaware-convo-1-sp-003"),  # May she protect us. / By her will... may it be in our lifetime.
        ("scrmd-gam-nor-scar-forest-combat-enemy-convo-1-sp-002", "scrma-gen-enmy-rspns-frstrtd-1x-sp-007"),    # May she guide us. / She tests us.
        ("scrmd-gam-nor-scar-forest-combat-enemy-convo-1-sp-002", "scrma-gam-sle-search-aware-convo-2-sp-003"),  # May she guide us. / May she bring us victory...
        ("scrmd-gam-nor-scar-forest-combat-enemy-convo-1-sp-002", "scrma-gam-nor-search-unaware-convo-1-sp-003"),   # May she guide us. / May the current be calm...
    ],
}
COMMENTS = {
    "mlt": [
        "mltma-gen-enmy-rspns-frstrtd-1x-sp-008",                       # I'm sleeping for a week after this.
        "mltma-gen-enmy-rspns-frstrtd-1x-sp-004",                       # Just want this to be over, man.
        "mltma-gen-enmy-rspns-frstrtd-1x-sp-005",                       # Here we go again.
        "mltma-gam-flo-search-aware-convo-1-sp-005",                    # Yeah. So let's keep it together so we don't get shot. Okay?
        "mltma-gam-nor-hospital-search-aware-convo-1-sp-004",           # You'd be dead. I'm telling you, these people are dangerous.
        "mltma-gen-enmy-srch-start-thrt-unwr-sp-010",                   # Be ready for anything.
        "mltma-gen-enmy-srch-start-thrt-unwr-sp-015",                   # Don't take any chances.
        "mltma-gen-enmy-srch-start-rspns-confident-1x-sp-003",          # Let's lock this shit down.
        "mltma-gen-enmy-srch-start-rspns-confident-1x-sp-014",          # Time to earn our keep.
    ],
    "scr": [
        "scrma-gam-flo-search-aware-convo-4-sp-002",                    # Don't let fear cloud your focus.
        "scrma-gam-flo-search-unaware-convo-4-sp-004",                  # Never let your guard down while in their midst.
        "scrma-gam-fob-hostile-territory-search-unaware-convo-2-sp-003",   # Whatever it is, we'll find out.
        "scrma-gam-fob-on-foot-trains-search-unaware-convo-1-sp-002",   # I long for the day they're gone.
        "scrma-gam-fob-on-foot-trains-search-unaware-convo-1-sp-001",   # Damned Wolves.
        "scrma-gam-sle-search-unaware-convo-2-sp-002",                  # Focus on what's in front of you.
        "scrma-gam-nor-search-unaware-convo-2-sp-003",                  # Let's set them free.
        "scrma-gam-flo-search-unaware-convo-4-sp-001",                  # Keep eyes on the high points.
        "scrma-gam-sle-search-forest-village-unaware-convo-1-sp-002",   # They are getting desperate...
    ],
}


def _norm(t):
    return re.sub(r"\s+", " ", t.replace("\u2019", "'").replace("?", "'")).strip().lower()


_ALL_TEXTS = {}


def all_texts(idx):
    """stream key -> subtitle text of every voice (male + female, both factions)"""
    if _ALL_TEXTS:
        return _ALL_TEXTS
    by_hash = {int(v[0], 16): k for k, v in idx.items()}
    chars = os.path.join(GAMEBIN, "dc1", "vox", "characters")
    _ALL_TEXTS.update(voice_texts([os.path.join(chars, "any-%s-%s.bin" % (f, g)) for f in ("militia", "scar") for g in ("male", "female")], by_hash))
    return _ALL_TEXTS


def exchange_lines(kind, fac, female, idx, texts):
    """the records of one exchange kind / faction, in table order: [{kind, fac, n, src, text, ids, speech}] - speech = 4 stream keys (voices a..d)"""
    refs = {"xstmt": [a for a, _ in PAIRS[fac]], "xrply": [b for _, b in PAIRS[fac]], "xcomm": COMMENTS[fac]}[kind]
    g = "f" if female else "m"
    bytext = {}
    for k, t in texts.items():
        bytext.setdefault((k.split("-")[0], _norm(t)), []).append(k)
    out = []
    for n, ref in enumerate(refs, 1):
        assert ref in idx and texts.get(ref, "").strip(), ("exchange line has no stream / text", ref)
        want = _norm(texts[ref])
        base = ref.split("-", 1)[1]
        keys = []
        for vv in VOICES:
            pre = "%s%s%s" % (fac, g, vv)
            k = pre + "-" + base
            if not (k in idx and _norm(texts.get(k, "")) == want):
                c = sorted(x for x in bytext.get((pre, want), []) if x in idx)
                k = c[0] if c else None
            keys.append(k)
        have = [k for k in keys if k]
        assert have, ("exchange line missing in the %s voices" % ("female" if female else "male"), ref, texts[ref])
        keys = [k or have[0] for k in keys]                     # a voice without that line: the nearest voice of the gender that has it
        out.append({"kind": kind, "fac": fac, "n": n, "src": ref.split("-", 1)[1], "text": texts[ref].strip(),
                    "ids": ["t2r-vox-%s%s%s-%s-%02d" % (fac, g, vv, kind, n) for vv in VOICES], "speech": keys})
    return out


# kinds without female lines (a female speaker falls back to the male voice lines; no female pool exists for them)
KILLCALL_KINDS = ("allykillmt", "allykillms", "allykillft", "allykillfs")
NOFEM_KINDS = ("reload", "noammo") + KILLCALL_KINDS
RELOAD_KINDS = ("reload", "noammo")                         # NOFEM for the MALE regen (genx), but the female voices have the same cmbt-flnk-rspns-cpr numbers: female lines too
THROW_KINDS = ("throwwarn", "throwmolo", "throwbomb", "throwsmoke", "smokewarn")   # male + female (female = every line of the category with all 4 voices)
WIN_KINDS = ("fewleft", "matchwon", "rapid")                 # male + female (the female lines are the SAME line numbers of the categories, see NUMF_KINDS)
PULL_KINDS = ("xbpull",)                                    # male + female (same line numbers of the category in all voices)
NUMF_KINDS = WIN_KINDS + PULL_KINDS + RELOAD_KINDS                                       # female pool = only the line numbers listed in POOLS (female numbering of these categories equals the male one)
# kind -> faction -> [(gen-enmy category, [line numbers] or None = every line with a subtitle text)]
# Picked by subtitle text (voice a; dc1/vox/characters/any-militia-male.bin / any-scar-male.bin): no lines about
# "her" / "she" (the SP target is Ellie / Abby; Seraphite "She" = the Prophet is fine), no {Name!} lines, no Infected.
POOLS = {
    "intro": {
        "mlt": [("srch-start-sp", [1, 2, 5, 7, 8, 11, 13, 14, 15, 16])],
        "scr": [("srch-start-sp", None)],
    },
    "introrsp": {
        "mlt": [("srch-start-rspns-confident-1x-sp", [1, 2, 3, 5, 6, 7, 9, 10, 12, 13, 14])],
        "scr": [("srch-start-rspns-confident-1x-sp", None)],
    },
    "mark": {
        "mlt": [("spot-plyr-plrl-pr", None), ("spot-plyr-unknown-pr", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12]),
                ("spot-2nd-attacker-pr", [3, 5, 6, 7]), ("callout-loc-far-pr", None),
                ("cmbt-callout-attack-plyr-cmd-plrl-cpr", [1, 3, 4, 6, 9, 11, 12])],
        "scr": [("spot-plyr-plrl-pr", None), ("spot-plyr-unknown-pr", None),
                ("spot-2nd-attacker-pr", [1, 2, 3, 7, 9]), ("callout-loc-far-pr", None),
                ("cmbt-callout-attack-plyr-cmd-plrl-cpr", None)],
    },
    "heal": {
        "mlt": [("heal-self-finish-sp", None), ("heal-self-finish-spj", None)],
        "scr": [("heal-self-finish-sp", None), ("heal-self-finish-spj", None)],
    },
    "kill": {
        "mlt": [("see-cmbt-kill-taunt-pr", [2, 9]), ("cmbt-infctd-kill-pr", [1]),
                ("cmbt-infctd-kill-taunt-spj", [1, 2, 3, 5])],
        "scr": [("see-cmbt-kill-taunt-pr", [1, 2, 3, 4, 7]), ("cmbt-infctd-kill-pr", [1, 3, 4]),
                ("cmbt-infctd-kill-taunt-sp", [2, 4, 5, 6])],
    },
    "down": {
        "mlt": [("cmbt-taunt-plyr-cvr-pr", [2, 8, 10]), ("see-cmbt-kill-taunt-pr", [3, 7, 12])],
        "scr": [("cmbt-taunt-plyr-cvr-pr", [7, 9, 10]), ("see-cmbt-kill-taunt-pr", [5, 6, 8, 10])],
    },
    "downed": {
        "mlt": [("cmbt-enmy-shot-cpr", None), ("cmbt-mtshld-grbbed-scared-sp", [1, 2, 3, 4, 5, 6, 7, 8])],
        "scr": [("cmbt-enmy-shot-pr", None), ("cmbt-enmy-shot-spj", None),
                ("cmbt-mtshld-grbbed-scared-sp", [1, 2, 3, 5, 7, 8, 9, 10])],
    },
    "revive": {
        "mlt": [("help-enmy-ally-pr", None)],
        "scr": [("help-enmy-ally-pr", [2, 3, 4, 5, 6, 7, 8])],
    },
    "thanks": {
        "mlt": [("help-enmy-ally-reply-sp", None)],
        "scr": [("help-enmy-ally-reply-sp", None)],
    },
    "allydown": {
        "mlt": [("callout-dead-ally-gnrc-spj", [1, 2, 4, 5])],
        "scr": [("callout-dead-ally-gnrc-spj", [4, 16, 17]), ("callout-dead-ally-addtnl-spj", [8])],
    },
    # Reactions to a teammate's execution ("No!" / "<Name>, no!!" / "<Name>!!"); the name kinds are the TLOU2 human
    # enemies' own name calls (gen-enmy-name-dead-ally-awr-<mal|fem>-spj-001-<name>, 16 names per faction, same names in all 4 voices),
    # NAMES = every name of the faction in alphabetical order (the line index is the name)
    "allyexecno": {
        # The shock-shout pool of a teammate's death / going down (short, unnamed): the whole fnd-dead-ally-inspct-slf shock set minus "Hey. Hey!" and
        # "Son of a bitch...!"; the female voices use the same category (NUMF-less: every female line of it, FEM_PER_CAT)
        "mlt": [("fnd-dead-ally-inspct-slf", [1, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 15])],
        "scr": [("fnd-dead-ally-inspct-slf", [3, 4, 5, 7, 8, 9, 12])],
    },
    # The killer callout of a teammate's death = TLOU2's own `callout-dead-ally-awr-<mal|fem>-spj-NNN` lines ("{Name!} They got him!": the
    # {Name!} is a separate name stream = our allyexecname kinds, the tail is what these hold), by the victim's gender and the pronoun. The engine plays
    # them natively too (random speaker, random name; not silenced yet: t2r-ext vx_dead_tick logs who asks). Numbering differs per faction.
    "allykillmt": {"mlt": [("callout-dead-ally-awr-mal-spj", [1, 2, 3])], "scr": [("callout-dead-ally-awr-mal-spj", [1, 2])]},
    "allykillms": {"mlt": [("callout-dead-ally-awr-mal-spj", [4, 5])], "scr": [("callout-dead-ally-awr-mal-spj", [3, 4, 5])]},
    "allykillft": {"mlt": [("callout-dead-ally-awr-fem-spj", [1, 2, 3])], "scr": [("callout-dead-ally-awr-fem-spj", [1, 2, 3])]},
    "allykillfs": {"mlt": [("callout-dead-ally-awr-fem-spj", [4, 5])], "scr": [("callout-dead-ally-awr-fem-spj", [4, 5, 6])]},
    "allyexecnamem": {"mlt": [("name-dead-ally-awr-mal-spj", "NAMES")], "scr": [("name-dead-ally-awr-mal-spj", "NAMES")]},
    "allyexecnamef": {"mlt": [("name-dead-ally-awr-fem-spj", "NAMES")], "scr": [("name-dead-ally-awr-fem-spj", "NAMES")]},
    # Marking an enemy bomb should give a voiceline: the WLF / Seraphite voices have no trap / mine / bomb callout (searched every
    # subtitle of any-militia-* / any-scar-*: only "Traps?" in a scripted chat and "Fire bomb!" / "Molotov!" for a thrown molotov), so the
    # mark of an enemy bomb takes their warn-an-ally barks (Look out! / Watch out! / Watch it! / Heads up! / Careful! / Eyes open!)
    "bomb": {
        "mlt": [("spot-warn-enmy-ally-pr", [1, 3, 4, 5, 6, 7])],
        "scr": [("spot-warn-enmy-ally-pr", [2, 3, 5, 6, 7])],
    },
    # Immersion pass: TLOU2's human enemies have no reload / out-of-ammo / throw barks of their own (the "out-of-ammo" categories are
    # about THE PLAYER being out: "She's out!"), so the team calls take the closest real lines: a covering request for a reload, the
    # molotov warn-ally lines (see-mltv) for an enemy throw
    "reload": {
        "mlt": [("cmbt-flnk-rspns-cpr", [12, 8])],
        "scr": [("cmbt-flnk-rspns-cpr", [5])],
    },
    "noammo": {
        "mlt": [("cmbt-flnk-rspns-cpr", [8, 12])],
        "scr": [("cmbt-flnk-rspns-cpr", [5, 11])],
    },
    "throwwarn": {
        "mlt": [("see-mltv-pr", [2, 3, 4, 5, 6, 7])],
        "scr": [("see-mltv-pr", [1, 2, 3, 4, 5, 6, 7, 8])],
    },
    # TLOU2's human enemies have NO own-throw barks (searched every subtitle of any-militia-* / any-scar-*), so our own throws take their
    # attack / advance orders: fire -> "Light 'em up!" / "Purge them!" (the Seraphite purge), bombs -> "Take them out!" / "Wipe them out!", smoke / stun ->
    # "Move in!" / "Push in!". The warnings of an ENEMY's throw are real: see-mltv (molotov), see-smoke-bmb (smoke); a pipe / stun bomb has none, it takes
    # the warn-ally barks (kind bomb).
    "throwmolo": {
        "mlt": [("cmbt-callout-attack-plyr-cmd-plrl-cpr", [3, 12, 1])],
        "scr": [("cmbt-callout-attack-plyr-cmd-plrl-cpr", [14, 5, 2])],
    },
    "throwbomb": {
        "mlt": [("cmbt-callout-attack-plyr-cmd-plrl-cpr", [1, 12, 8, 13])],
        "scr": [("cmbt-callout-attack-plyr-cmd-plrl-cpr", [5, 12, 15, 1])],
    },
    "throwsmoke": {
        "mlt": [("cmbt-advnc-cmd-cpr", [1, 7, 5])],
        "scr": [("cmbt-advnc-cmd-cpr", [1, 5])],
    },
    "smokewarn": {
        "mlt": [("see-smoke-bmb-pr", [1, 2, 5, 7])],
        "scr": [("see-smoke-bmb-pr", [1, 2, 5, 7])],
    },
    # TLOU2's human enemies have no "few enemies left" / "we won" / "multi kill" barks (searched every subtitle of any-militia-* / any-scar-*),
    # so: few left = pushing the last ones (advance orders "Keep up the pressure!" / "Don't let up!", the suppress barks "No mercy!" / "Don't stop!"), match
    # won = the done / cleared barks ("We're done here." / "Looks like this place is clear." / "Done!" / "It is done!" / "She guides me!" / "All cleaned out."),
    # rapid kill = the second-attacker barks ("Another one!" / "We got another one!" / "Another Wolf!" / "Got another Wolf!"). No "her / she" about the player.
    "fewleft": {
        "mlt": [("cmbt-advnc-cmd-cpr", [3, 4, 8]), ("prst-reinforcement-ally-call-pr", [4])],
        "scr": [("cmbt-advnc-cmd-cpr", [3, 4, 5]), ("cmbt-plyr-suppressed-cpr", [5, 10])],
    },
    "matchwon": {
        "mlt": [("patrol-pair-clear-sp", [7, 11]), ("rspns-intns-pr", [4, 5, 6]), ("patrol-pair-factn-clear-sp", [7])],
        "scr": [("patrol-pair-clear-sp", [8]), ("rspns-intns-pr", [6, 8, 11]), ("patrol-pair-scvng-clear-sp", [4])],
    },
    "rapid": {
        "mlt": [("spot-2nd-attacker-pr", [2, 3, 7, 10])],
        "scr": [("spot-2nd-attacker-pr", [1, 5, 8, 9, 10])],
    },
    # Pulling a crossbow bolt out of our own body. TLOU2's human enemies have no arrow / pain-murmur barks, but the human-shield scared lines are
    # exactly the horrified half-voiced "Oh god... Oh jesus... Oh no..." (WLF) / "Protect me... She guides me... Brace me..." (Seraphite prayers) said through the teeth
    "xbpull": {
        "mlt": [("cmbt-mtshld-grbbed-scared-sp", [5, 6, 7, 1, 3, 9])],
        "scr": [("cmbt-mtshld-grbbed-scared-sp", [5, 6, 7, 2, 8, 10])],
    },
    "last": {
        "mlt": [("rspns-afraid-1x-sp", [1, 2, 7, 10, 12, 13])],
        "scr": [("rspns-afraid-1x-sp", [1, 2, 3, 7, 11, 12])],
    },
}


# ---------------------------------------------------------------------------------------------------------------- Seraphite whistles
# All Seraphite whistles mean something and are used widely: TLOU2's Seraphites talk to each other in whistles, and every whistle is a SPEECH STREAM
# of the same speech1 archive (<voice>-eff-gen-<ai category>-whstl-<variant>-NNN, an 'effort' record without subtitle; only voices scrma / scrfa have
# them - a whistle sounds the same whoever whistles, so all 4 of our voice records of a whistle line point at the a stream; plus the few neutral
# scrm-gen-enmy-*-whstl-* streams, male). So they play through the very same vox record / `say` / msg 10 path as spoken lines (no SFX path needed).
# Their meaning is the SP AI category they belong to (what a Seraphite whistles in that situation in the game):
#   spot-plyr-whstl-pr / pursue-spot-plyr-near-whstl-pr   "I see the enemy" (near)            -> mark, warnings
#   pursue-spot-plyr-far-whstl-pr                           "enemy far away" (subtitle 'Ambush whistle') -> mark
#   pursue-spot-plyr-rally-whstl-pr                         'Rally whistle' (gather / regroup)       -> intro, few left, match won
#   attack-plyr-cmd-whstl-cpr                               attack order                             -> down, throw orders, rapid kill, few left
#   pursue-reinforcement-call-whstl-pr / cmbt-rnfrcmnt-call "send help / reinforcements!"           -> we went down, out of ammo
#   invstgt-fnd-dead-ally-inform / -reactn-1 / -reactn-2    "found a dead ally" tell + grief         -> ally down, ally executed, last teammate
#   invstgt-ally-mssng-cncrnd-whstl-spj                     "where is my ally?" (concerned)          -> we revive a teammate
#   srch-check-in-annnc / invstgt-check-in-annnc            check-in "I'm here, all well"            -> healed, thanks
#   srch-check-in-fnd-nthng (sp / spj)                      "found nothing / all clear"              -> kill, match won
#   srch-check-in-far / -far-rspns                          far check-in and its answer              -> match start answer, thanks
#   pursue-trgt-mssng-whstl-pr                              "target lost"                            -> last teammate
#   invstgt-strt-annnc / strt-cmd / pair-strt               search start announce / order            -> match start
#   cmbt-flnk-whstl-cpr (neutral male stream)               "flanking"                               -> reload, smoke push
# WHISTLES[kind] = [(category, cap)]; lines of a kind: the spoken pool first, the whistles as the TAIL of the same (faction, kind) range (t2r-ext
# VX_NW / VXF_NW = how many tail lines are whistles; the picker decides whistle vs spoken, see vx_pick_slot_g).
WHISTLES = {
    "intro": [("pursue-spot-plyr-rally-whstl-pr", 8), ("invstgt-strt-annnc-whstl-slf", 4), ("invstgt-strt-cmd-whstl-wh", 3)],
    "introrsp": [("srch-check-in-far-rspns-whstl-pr", 8), ("invstgt-check-in-annnc-whstl-spj", 4)],
    "mark": [("spot-plyr-whstl-pr", 8), ("pursue-spot-plyr-near-whstl-pr", 8), ("pursue-spot-plyr-far-whstl-pr", 6)],
    "heal": [("srch-check-in-annnc-whstl-sp", 6)],
    "kill": [("srch-check-in-fnd-nthng-whstl-sp", 6), ("attack-plyr-cmd-whstl-cpr", 4)],
    "down": [("attack-plyr-cmd-whstl-cpr", 8)],
    "downed": [("pursue-reinforcement-call-whstl-pr", 8)],
    "revive": [("invstgt-ally-mssng-cncrnd-whstl-spj", 6)],
    "thanks": [("srch-check-in-far-rspns-whstl-pr", 4), ("srch-check-in-annnc-whstl-spj", 3)],
    "allydown": [("invstgt-fnd-dead-ally-inform-whstl-cpr", 6), ("invstgt-fnd-dead-ally-reactn-whstl-1-cpr", 6)],
    "allyexecno": [("invstgt-fnd-dead-ally-reactn-whstl-2-cpr", 6)],
    "last": [("invstgt-fnd-dead-ally-reactn-whstl-2-cpr", 6), ("pursue-trgt-mssng-whstl-pr", 4)],
    "fewleft": [("attack-plyr-cmd-whstl-cpr", 6), ("pursue-spot-plyr-rally-whstl-pr", 3)],
    "matchwon": [("srch-check-in-fnd-nthng-whstl-spj", 6), ("pursue-spot-plyr-rally-whstl-pr", 3)],
    "rapid": [("attack-plyr-cmd-whstl-cpr", 6)],
    "bomb": [("pursue-spot-plyr-near-whstl-pr", 6)],
    "throwwarn": [("pursue-spot-plyr-near-whstl-pr", 6), ("spot-plyr-whstl-pr", 4)],
    "smokewarn": [("pursue-spot-plyr-near-whstl-pr", 6)],
    "throwmolo": [("attack-plyr-cmd-whstl-cpr", 6)],
    "throwbomb": [("attack-plyr-cmd-whstl-cpr", 6)],
    "throwsmoke": [("attack-plyr-cmd-whstl-cpr", 4), ("cmbt-flnk-whstl-cpr", 1)],
    "reload": [("cmbt-flnk-whstl-cpr", 1), ("srch-check-in-annnc-whstl-sp", 3)],
    "noammo": [("pursue-reinforcement-call-whstl-pr", 4), ("cmbt-rnfrcmnt-call-whstl-cpr", 1)],
}
WHISTLE_MS = 1200                     # VX_DUR of a whistle line (no subtitle to estimate from)
# neutral male streams (scrm-gen-enmy-<cat>-NNN, no voice letter) of categories that have no scrma stream
NEUTRAL_WH = ("cmbt-flnk-whstl-cpr", "cmbt-rnfrcmnt-call-whstl-cpr")


def whistle_lines(kind, fem, idx):
    """-> [(src, [stream key] * 4)] of the Seraphite whistles of `kind` (male: scrma + neutral scrm streams, female: scrfa), numbers spread per category"""
    out = []
    for cat, cap in WHISTLES.get(kind, ()):
        if cat in NEUTRAL_WH:
            if fem:
                continue
            keys = sorted(k for k in idx if re.match(r"^scrm-gen-enmy-%s-\d+$" % re.escape(cat), k))
        else:
            pre = "scrfa" if fem else "scrma"
            keys = sorted(k for k in idx if re.match(r"^%s-eff-gen-%s-\d+$" % (pre, re.escape(cat)), k))
        # the speech index lists streams whose audio is NOT in english.psarc (silent when played): only streams really in the archive
        keys = [k for k in keys if idx[k][0] in _eng_names()]
        for k in _spread(keys, cap):
            out.append((k, [k] * 4))
    return out


_ENG = []


def _eng_names():
    if not _ENG:
        _ENG.append(psarc_names(os.path.join(GAME, "build", "pc", "main", "speech1", "english.psarc")))
    return _ENG[0]


def add_whistles(lines, fem):
    """a vox_lines json list -> the same with the Seraphite whistle lines appended to the end of each scr kind range (old whistle lines dropped first)"""
    idx = json.load(open(os.path.join(GAME, "build", "pc", "main", "speech1", "english.xvag-index.json")))
    lines = [l for l in lines if not l.get("whistle")]
    last = {}
    for i, l in enumerate(lines):
        last[(l["fac"], l["kind"])] = i
    out = []
    for i, l in enumerate(lines):
        out.append(l)
        if l["fac"] == "scr" and last[("scr", l["kind"])] == i and l["kind"] in WHISTLES:
            n = l["n"]
            seen = set()
            for src, keys in whistle_lines(l["kind"], fem, idx):
                if src in seen:         # (the same stream listed under two categories of one kind)
                    continue
                seen.add(src)
                n += 1
                ids = ["t2r-vox-%s%s-%s-%02d" % ("scrf" if fem else "scrm", v, l["kind"], n) for v in VOICES]
                out.append({"kind": l["kind"], "fac": "scr", "n": n, "src": src, "text": "(whistle)", "whistle": True, "ids": ids, "speech": keys})
    return out


def gen_whistles():
    """(dev, needs the game's speech index) add / refresh the Seraphite whistle lines of both json files + headers; the spoken lines stay as committed"""
    male = add_whistles(json.load(open(DATA)), False)
    json.dump(male, open(DATA, "w"), indent=1)
    write_header(male)
    f = json.load(open(FDATA))
    fl = add_whistles(f["lines"], True)
    json.dump({"lines": fl, "effort": f["effort"]}, open(FDATA, "w"), indent=1)
    write_female_header(fl, f["effort"])
    print("whistles: male %d, female %d" % (sum(1 for l in male if l.get("whistle")), sum(1 for l in fl if l.get("whistle"))))


def fnv(s):
    h = 0xCBF29CE484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def voice_texts(paths, keys_by_hash):
    """speech key -> subtitle text: vox/characters records [speech sid][subtitle sid][0][char *text]['neutral']."""
    sys.path.insert(0, HERE)
    from dcfile import DcFile
    neutral = fnv("neutral")
    out = {}
    for p in paths:
        b = open(p, "rb").read()
        d = DcFile(b)
        for a in range(0x18, d.size - 0x10, 8):
            if d.q(a + 8) == neutral and d.is_ptr(a) and d.q(a - 8) == 0 and d.q(a - 0x18) in keys_by_hash:
                q = d.q(a)
                if d.strings <= q < d.size:
                    out[keys_by_hash[d.q(a - 0x18)]] = b[q:b.index(b"\0", q)].decode("utf-8", "replace")
    return out


def gen(only=None):
    """only = a tuple of kind names: just those kinds are (re)generated, every other kind keeps its lines of data/vox_lines.json
    (the committed lines are not touched when the game data has moved on: `genx`)"""
    old = json.load(open(DATA)) if only else []
    idx =json.load(open(os.path.join(GAME, "build", "pc", "main", "speech1", "english.xvag-index.json")))
    for k, v in idx.items():         # the index hash is fnv64 of the stream name (checked here)
        assert int(v[0], 16) == fnv(k), k
        break
    by_hash = {int(v[0], 16): k for k, v in idx.items()}
    chars = os.path.join(GAMEBIN, "dc1", "vox", "characters")
    texts = voice_texts([os.path.join(chars, "any-militia-male.bin"), os.path.join(chars, "any-scar-male.bin")], by_hash)
    lines = []
    for ki, (kind, _) in enumerate(KINDS):
        if only and kind not in only:
            lines.extend(l for l in old if l["kind"] == kind)
            continue
        for fi, fac in enumerate(FACTIONS):
            n = 0
            if kind in EXCH_KINDS:
                lines.extend(exchange_lines(kind, fac, False, idx, all_texts(idx)))
                continue
            for cat, nums in POOLS[kind][fac]:
                if nums == "NAMES":
                    names = sorted(m.group(1) for k in idx for m in [re.match(r"^%sma-gen-enmy-%s-001-([a-z]+)$" % (fac, re.escape(cat)), k)] if m)
                    for nm in names:
                        keys = ["%sm%s-gen-enmy-%s-001-%s" % (fac, v, cat, nm) for v in VOICES]
                        if [k for k in keys if k not in idx]:
                            print(f"skip name {nm}: not in all voices")
                            continue
                        n += 1
                        lines.append({"kind": kind, "fac": fac, "n": n, "src": "%s-001-%s" % (cat, nm), "text": nm.capitalize() + "!",
                                      "ids": ["t2r-vox-%sm%s-%s-%02d" % (fac, v, kind, n) for v in VOICES], "speech": keys})
                    continue
                have = sorted(int(m.group(1)) for k in texts
                              for m in [re.match(r"^%sma-gen-enmy-%s-(\d+)$" % (fac, re.escape(cat)), k)] if m)
                for num in (have if nums is None else nums):
                    base = "gen-enmy-%s-%03d" % (cat, num)
                    keys = ["%sm%s-%s" % (fac, v, base) for v in VOICES]
                    a = keys[0]
                    assert a in texts, f"{a}: no subtitle text (not a line of voice a)"
                    missing = [k for k in keys if k not in idx]
                    if missing:
                        print(f"skip {base}: no stream for {missing}")
                        continue
                    n += 1
                    lines.append({"kind": kind, "fac": fac, "n": n, "src": base, "text": texts[a].strip(),
                                  "ids": ["t2r-vox-%sm%s-%s-%02d" % (fac, v, kind, n) for v in VOICES], "speech": keys})
            assert n, (kind, fac)
    lines = add_whistles(lines, False)
    json.dump(lines, open(DATA, "w"), indent=1)
    write_header(lines)
    print(f"{len(lines)} lines x 4 voices -> {DATA}, {HEADER}")


def write_header(lines):
    o = ["// GENERATED by tools/features/vox_lines.py gen - do not edit. Team voice lines (t2r-ext vx_*):",
         "// VX_LINES[i].h[v] = fnv64 line id of voice v (a..d) = a vox-info record dc_data_patches.patch_vox_lines adds to",
         "// vox-igc-greenlight.bin; VX_RANGE[faction 0 Seraphite / 1 WLF][kind] = {first, count} in VX_LINES.",
         "#define VX_NKINDS %d" % len(KINDS)]
    for ki, (k, why) in enumerate(KINDS):
        o.append("#define VX_%s %d   // %s" % (k.upper(), ki, why))
    o.append("typedef struct { uint64_t h[4]; } vx_line_t;")
    o.append("static const vx_line_t VX_LINES[] = {")
    rng = {}
    for i, l in enumerate(lines):
        key = (FACTIONS.index(l["fac"]), [k for k, _ in KINDS].index(l["kind"]))
        f, c = rng.get(key, (i, 0))
        rng[key] = (f, c + 1)
        o.append("    {{%s}},   // %s %s: %s" % (", ".join("0x%016xULL" % fnv(x) for x in l["ids"]), l["ids"][0],
                                               l["src"], l["text"].replace("\\", "/").encode("ascii", "replace").decode()))
    o.append("};")
    o.append("// spoken length estimate (ms) per line from its subtitle text (~15 chars/s + lead/tail): t2r-ext's voice scheduler")
    o.append("static const uint16_t VX_DUR[] = {%s};" % ", ".join(str(WHISTLE_MS if l.get("whistle") else 350 + 66 * len(l["text"].strip())) for l in lines))
    o.append("static const uint16_t VX_RANGE[2][VX_NKINDS][2] = {")
    for f in range(2):
        o.append("    {%s}," % ", ".join("{%d, %d}" % rng[(f, k)] for k in range(len(KINDS))))
    o.append("};")
    o.append("// VX_NW[faction][kind] = how many lines at the END of the range are Seraphite whistles (no speech, see vox_lines.py WHISTLES)")
    o.append("static const uint8_t VX_NW[2][VX_NKINDS] = {")
    for f in range(2):
        o.append("    {%s}," % ", ".join(str(sum(1 for l in lines if l.get("whistle") and FACTIONS.index(l["fac"]) == f and l["kind"] == k)) for k, _ in KINDS))
    o.append("};")
    open(HEADER, "w", newline="\n").write("\n".join(o) + "\n")


def load():
    return json.load(open(DATA))


# ------------------------------------------------------------------------------------------------ female voices
# Female player characters (re/female-characters.md, T2R_FEMALE=1 / t2r-female.txt): the same 11 team-line kinds in the four
# TLOU2 FEMALE enemy voices (WLF mltfa..mltfd = soundbank4 vox-militia-female-a..d, Seraphites scrfa..scrfd = vox-scar-female-a..d)
# plus the EFFORT kinds the male players get from the engine ("say" of a generic vox-eff-gen-* event): a melee effort, a pain
# line, a death line and a throat / neck-cut death line. Both are vox-info records of the mod's vox-igc-greenlight module (same
# mechanism as the male lines: the speech key is a stream name of speech1/<language>.xvag-index.json, no sound bank involved).
# Female stream numbering differs from the male one, so there is no hand-picked list: every line of the category that has all four
# voices and a subtitle text passing FEM_BAD (no "she / her" about the player, no {Name!} lines, no Infected) is a candidate,
# at most FEM_PER_CAT per category (evenly spread). Efforts have no subtitle: any numbered stream of the category with all 4 voices.
FDATA = os.path.join(HERE, "data", "vox_lines_female.json")
FHEADER = os.path.join(ROOT, "tools", "ext", "vox_lines_female.h")
FEM_PER_CAT = 10
FEM_BAD_WORDS = re.compile(r"\b(she|she's|her|hers|herself|ellie|abby|infected|clicker|clickers|runner|runners|bloater|shambler|stalker|freak|freaks|mushroom|mushrooms|fungus|fungal|spore|spores)\b", re.I)
FEM_BAD_NAME = re.compile(r"\{[A-Z]")                     # {Name!} slots (stage directions like {wince} are lower case and fine)
# effort kinds: (name, what plays it, per faction [(category, per-category cap)])
EFFORT_KINDS = [
    ("give", "melee blow / execution effort (ex_grunt, gx_play GXS_EFFORT)",
     [("fight-give-med", 6), ("fight-give-lrg-shrt", 6), ("fight-give-sml", 4), ("fight-give-hvy-shrt", 4)]),
    ("pain", "melee pain of an execution victim / a hit (gx_play GXS_PAIN)",
     [("fight-take-med", 6), ("fight-take-sml", 5), ("fight-take-lrg", 5), ("hit-by-gun-flinch", 4)]),
    ("death", "death line (gx_play death; shots / blunt)",
     [("death-pistol", 3), ("death-rifle", 3), ("death-shtgn", 3), ("death-blnt-lrg", 3), ("death-hdsht", 3), ("death-whine-sml", 2)]),
    ("deathknife", "death by a blade (the shiv / knife pairs)",
     [("death-throat-slit", 5), ("death-neck-stab", 5), ("death-bloody-gut-stab", 4), ("death-shrp-stab", 2)]),
]


def _spread(seq, cap):
    """at most `cap` items of seq, evenly spread (keeps the first and the last)"""
    if len(seq) <= cap:
        return list(seq)
    return [seq[round(i * (len(seq) - 1) / (cap - 1))] for i in range(cap)] if cap > 1 else seq[:1]


def female_ok(text):
    t = text.strip()
    return bool(t) and not FEM_BAD_WORDS.search(t) and not FEM_BAD_NAME.search(t)


def gen_female(only=None):
    """(dev, needs the game + re/gamebin) -> data/vox_lines_female.json + ../ext/vox_lines_female.h
    only = a tuple of kind names: just those kinds are regenerated, every other kind and the efforts stay as committed (`genfx`)"""
    old = json.load(open(FDATA)) if only else None
    idx = json.load(open(os.path.join(GAME, "build", "pc", "main", "speech1", "english.xvag-index.json")))
    by_hash = {int(v[0], 16): k for k, v in idx.items()}
    chars = os.path.join(GAMEBIN, "dc1", "vox", "characters")
    texts = voice_texts([os.path.join(chars, "any-militia-female.bin"), os.path.join(chars, "any-scar-female.bin")], by_hash)
    lines, eff = [], []
    for kind, _ in KINDS:
        if kind in NOFEM_KINDS and kind not in RELOAD_KINDS:
            continue
        if only and kind not in only:
            lines.extend(l for l in old["lines"] if l["kind"] == kind)
            continue
        for fac in FACTIONS:
            n = 0
            if kind in EXCH_KINDS:
                lines.extend(exchange_lines(kind, fac, True, idx, all_texts(idx)))
                continue
            for cat, _nums in POOLS[kind][fac]:
                cand = []
                for num in sorted(int(m.group(1)) for k in texts
                                  for m in [re.match(r"^%sfa-gen-enmy-%s-(\d+)$" % (fac, re.escape(cat)), k)] if m):
                    if kind in NUMF_KINDS and num not in _nums:
                        continue
                    base = "gen-enmy-%s-%03d" % (cat, num)
                    keys = ["%sf%s-%s" % (fac, v, base) for v in VOICES]
                    if kind == "allyexecno" and texts[keys[0]].strip() in ("Hey. Hey!", "Son of a bitch...!"):
                        continue
                    if all(k in idx for k in keys) and female_ok(texts[keys[0]]):
                        cand.append((base, keys, texts[keys[0]].strip()))
                for base, keys, text in _spread(cand, FEM_PER_CAT):
                    n += 1
                    lines.append({"kind": kind, "fac": fac, "n": n, "src": base, "text": text, "speech": keys,
                                  "ids": ["t2r-vox-%sf%s-%s-%02d" % (fac, v, kind, n) for v in VOICES]})
            assert n, ("female", kind, fac)
    if only:
        eff = old["effort"]
    for ek, _what, cats in (() if only else EFFORT_KINDS):
        for fac in FACTIONS:
            n = 0
            for cat, cap in cats:
                nums = sorted(int(m.group(1)) for k in idx for m in [re.match(r"^%sfa-eff-gen-%s-(\d+)$" % (fac, re.escape(cat)), k)] if m)
                nums = [x for x in nums if all("%sf%s-eff-gen-%s-%03d" % (fac, v, cat, x) in idx for v in VOICES)]
                for num in _spread(nums, cap):
                    n += 1
                    keys = ["%sf%s-eff-gen-%s-%03d" % (fac, v, cat, num) for v in VOICES]
                    eff.append({"kind": ek, "fac": fac, "n": n, "src": "eff-gen-%s-%03d" % (cat, num), "text": "", "speech": keys,
                                "ids": ["t2r-vox-%sf%s-eff-%s-%02d" % (fac, v, ek, n) for v in VOICES]})
            assert n, ("female effort", ek, fac)
    lines = add_whistles(lines, True)
    json.dump({"lines": lines, "effort": eff}, open(FDATA, "w"), indent=1)
    write_female_header(lines, eff)
    print(f"female: {len(lines)} team lines + {len(eff)} effort lines x 4 voices -> {FDATA}, {FHEADER}")


def write_female_header(lines, eff):
    o = ["// GENERATED by tools/features/vox_lines.py genf - do not edit. Female team voice lines + efforts (t2r-ext female_*, vx_*):",
         "// VXF_LINES[i].h[v] = fnv64 line id of female voice v (a..d: mltfa.. / scrfa..), VXF_RANGE[faction 0 Seraphite / 1 WLF][kind]",
         "// = {first, count} in VXF_LINES (kinds = vox_lines.h VX_*); VXE_* the same for the effort kinds. Needs vox_lines.h first.",
         "#define VXE_NKINDS %d" % len(EFFORT_KINDS)]
    for ki, (k, why, _) in enumerate(EFFORT_KINDS):
        o.append("#define VXE_%s %d   // %s" % (k.upper(), ki, why))

    def table(name, rows, kinds):
        o.append("static const vx_line_t %s[] = {" % name)
        rng = {}
        for i, l in enumerate(rows):
            key = (FACTIONS.index(l["fac"]), kinds.index(l["kind"]))
            f, c = rng.get(key, (i, 0))
            rng[key] = (f, c + 1)
            o.append("    {{%s}},   // %s %s: %s" % (", ".join("0x%016xULL" % fnv(x) for x in l["ids"]), l["ids"][0], l["src"],
                                                    l["text"].replace("\\", "/").encode("ascii", "replace").decode()))
        o.append("};")
        return rng
    rng = table("VXF_LINES", lines, [k for k, _ in KINDS])
    o.append("static const uint16_t VXF_DUR[] = {%s};" % ", ".join(str(WHISTLE_MS if l.get("whistle") else 350 + 66 * len(l["text"].strip())) for l in lines))
    o.append("static const uint16_t VXF_RANGE[2][VX_NKINDS][2] = {")
    for f in range(2):      # (a kind without female lines - the execution name calls - stays {0, 0}: the male lines play)
        o.append("    {%s}," % ", ".join("{%d, %d}" % rng.get((f, k), (0, 0)) for k in range(len(KINDS))))
    o.append("};")
    o.append("static const uint8_t VXF_NW[2][VX_NKINDS] = {      // whistle lines at the end of each range (see vox_lines.h VX_NW)")
    for f in range(2):
        o.append("    {%s}," % ", ".join(str(sum(1 for l in lines if l.get("whistle") and FACTIONS.index(l["fac"]) == f and l["kind"] == k)) for k, _ in KINDS))
    o.append("};")
    erng = table("VXE_LINES", eff, [k for k, _, _ in EFFORT_KINDS])
    o.append("static const uint16_t VXE_RANGE[2][VXE_NKINDS][2] = {")
    for f in range(2):
        o.append("    {%s}," % ", ".join("{%d, %d}" % erng[(f, k)] for k in range(len(EFFORT_KINDS))))
    o.append("};")
    open(FHEADER, "w", newline="\n").write("\n".join(o) + "\n")


def print_pairs():
    """review list: pair n = xstmt n + xrply n of each faction, then the comments (texts from data/vox_lines.json)"""
    d = load()
    for fac in FACTIONS:
        rows = {k: [l for l in d if l["kind"] == k and l["fac"] == fac] for k in EXCH_KINDS}
        print("== %s: %d pairs, %d comments" % ("WLF" if fac == "mlt" else "Seraphites", len(rows["xstmt"]), len(rows["xcomm"])))
        for a, b in zip(rows["xstmt"], rows["xrply"]):
            print("  %2d  %-34s -> %s" % (a["n"], a["text"], b["text"]))
        print("  comments: " + " / ".join(l["text"] for l in rows["xcomm"]))


def load_female():
    d = json.load(open(FDATA))
    return d["lines"] + d["effort"]


def female_records():
    """(line id, speech key) of every female record (patch_vox_lines' `lines`)"""
    return [(i, sp) for ln in load_female() for i, sp in zip(ln["ids"], ln["speech"])]


# ------------------------------------------------------------------------------------------------ per-language availability
# speech1/<language>.psarc holds only the streams the localisation recorded (Polish: 94k of English's 130k; no TLOU2 enemy bark variants
# like "Stop them!" / most "I see them!" spot lines). A key missing there is played from ENGLISH by the engine (e.g. "Stop them!" in
# English in a Polish game). genavail writes tools/ext/vox_avail.h: per language (every speech1/*.psarc but english) one byte per line
# (bit v = voice a..d has audio in that language) for VX_LINES / VXF_LINES / VXE_LINES; t2r-ext skips lines without audio in the voice
# language. A key that is not in the english archive either (played by other means) counts as available: no behaviour change for it.
AVAIL_HEADER = os.path.join(ROOT, "tools", "ext", "vox_avail.h")


def psarc_names(path):
    """the set of stream names (16 hex digits) of a plain big-endian zlib PSARC (the speech archives)"""
    import zlib
    f = open(path, "rb")
    magic, vmaj, vmin, comp, toc_len, esz, n, bsize, flags = struct.unpack(">4sHH4sIIIII", f.read(32))
    assert magic == b"PSAR", magic
    f.seek(0)
    toc = f.read(toc_len)
    bi, usz, off = (int.from_bytes(toc[32 + 16:32 + 20], "big"), int.from_bytes(toc[32 + 20:32 + 25], "big"),
                    int.from_bytes(toc[32 + 25:32 + 30], "big"))
    bt = 32 + n * 30
    bs = struct.unpack_from(">%dH" % ((toc_len - bt) // 2), toc, bt)
    out = bytearray()
    while len(out) < usz:
        cs = bs[bi] or bsize
        f.seek(off)
        blk = f.read(cs)
        want = min(bsize, usz - len(out))
        out += blk if cs == want else zlib.decompress(blk)
        off += cs
        bi += 1
    return {x for x in out.decode(errors="replace").split("\0") if x}


def gen_avail():
    sd = os.path.join(GAME, "build", "pc", "main", "speech1")
    idx = json.load(open(os.path.join(sd, "english.xvag-index.json")))
    eng = psarc_names(os.path.join(sd, "english.psarc"))
    male, fem = load(), json.load(open(FDATA))
    tabs = [("M", male), ("F", fem["lines"]), ("E", fem["effort"])]
    o = ["// GENERATED by tools/features/vox_lines.py genavail - do not edit. Which of our speech keys have audio in each non-English voice",
         "// language (speech1/<language>.psarc): VXA_<LANG>_{M,F,E}[line] = bit v (voice a..d); M = VX_LINES, F = VXF_LINES, E = VXE_LINES.",
         "// A line without audio is played from English by the engine, so t2r-ext skips it (vx_lang_missing)."]
    langs, rep = [], []
    # ENGLISH too - the english index lists keys whose stream is not in english.psarc (28 of 2032 male team-line voice takes, 72 of 540 female effort
    # takes: silent whatever `say` answers); bit v = the stream exists. (Other languages: absent from the language = the engine plays English, skipped as before.)
    for fn in ["english.psarc"] + [x for x in sorted(os.listdir(sd)) if x != "english.psarc"]:
        lang, ext = os.path.splitext(fn)
        if ext != ".psarc":
            continue
        english = lang == "english"
        have = eng if english else psarc_names(os.path.join(sd, fn))
        for t, rows in tabs:
            vals, miss = [], 0
            for ln in rows:
                m = 0
                for v, key in enumerate(ln["speech"]):
                    e = idx.get(key)
                    if ln.get("whistle") or not e or (e[0] in have if english else (e[0] not in eng or e[0] in have)):     # unknown / not in english: leave as is
                        m |= 1 << v
                    else:
                        miss += 1
                vals.append(m)
            o.append("static const uint8_t VXA_%s_%s[] = {%s};" % (lang.upper(), t, ",".join(str(x) for x in vals)))
            rep.append((lang, t, len(rows), miss))
        langs.append((lang, ["VXA_%s_%s" % (lang.upper(), t) for t, _ in tabs]))
    o.append("static const struct { const char *name; const uint8_t *m, *f, *e; } VXA_LANGS[] = {")
    for lang, ns in langs:
        o.append('    {"%s", %s},' % (lang, ", ".join(ns)))
    o.append("};")
    open(AVAIL_HEADER, "w", newline="\n").write("\n".join(o) + "\n")
    for r in rep:
        print("%s %s: %d lines, %d voice records without audio" % r)


# ------------------------------------------------------------------------------------------------ burning-death screams
# A molotov kill burns the victim with his OWN voice set's fire-death efforts: <voice>-eff-gen-death-fire-fast-NNN (a standing burn) /
# -slow-NNN (downed / lingering), every MP voice: militia + scar x male + female x a..d (3-15 takes each, counts differ per voice). No text,
# no kind table: one flat id table + a range per (faction, gender, voice, speed). The records are vox-info records like the others.
BDATA = os.path.join(HERE, "data", "vox_burn.json")
BHEADER = os.path.join(ROOT, "tools", "ext", "vox_burn.h")
BURN_SPEEDS = ("fast", "slow")


def gen_burn():
    """(needs the game's english.xvag-index.json) -> data/vox_burn.json + ../ext/vox_burn.h"""
    sd = os.path.join(GAME, "build", "pc", "main", "speech1")
    idx = json.load(open(os.path.join(sd, "english.xvag-index.json")))
    # The index lists keys whose stream is NOT in english.psarc (112 of 344: scrfa-...-fast-004..006, mltfb-...-fast-004, ...): `say` on those
    # answers 0 and is silent (A/B: both picked takes were -004 = no audio). Only takes with a stream are records.
    eng = psarc_names(os.path.join(sd, "english.psarc"))
    recs = []
    for fac in FACTIONS:
        for g in "mf":
            for v in VOICES:
                for sp in BURN_SPEEDS:
                    nums = sorted(int(m.group(1)) for k in idx
                                  for m in [re.match(r"^%s%s%s-eff-gen-death-fire-%s-(\d+)$" % (fac, g, v, sp), k)] if m and idx[k][0] in eng)
                    assert nums, (fac, g, v, sp)
                    for n, num in enumerate(nums, 1):
                        pre = "%s%s%s" % (fac, g, v)
                        recs.append({"fac": fac, "g": g, "v": v, "speed": sp, "n": n, "speech": "%s-eff-gen-death-fire-%s-%03d" % (pre, sp, num),
                                     "id": "t2r-vox-burn-%s-%s-%02d" % (pre, sp, n)})
    json.dump(recs, open(BDATA, "w"), indent=1)
    o = ["// GENERATED by tools/features/vox_lines.py genburn - do not edit. Burning-death screams (t2r-ext bd_scream): every MP voice's own",
         "// <voice>-eff-gen-death-fire-fast/slow-NNN takes. VXB_LINES[i] = fnv64 id of a vox-info record (dc_data_patches.patch_vox_burn);",
         "// VXB_RANGE[faction 0 Seraphite / 1 WLF][gender 0 male / 1 female][voice a..d][speed 0 fast / 1 slow] = {first, count} in VXB_LINES.",
         "static const uint64_t VXB_LINES[] = {"]
    rng = {}
    for i, r in enumerate(recs):
        key = (FACTIONS.index(r["fac"]), "mf".index(r["g"]), VOICES.index(r["v"]), BURN_SPEEDS.index(r["speed"]))
        f, c = rng.get(key, (i, 0))
        rng[key] = (f, c + 1)
        o.append("    0x%016xULL,   // %s <- %s" % (fnv(r["id"]), r["id"], r["speech"]))
    o.append("};")
    o.append("static const uint16_t VXB_RANGE[2][2][4][2][2] = {")
    for f in range(2):
        o.append("  {")
        for g in range(2):
            o.append("    {%s}," % ", ".join("{%s}" % ", ".join("{%d, %d}" % rng[(f, g, v, s)] for s in range(2)) for v in range(4)))
        o.append("  },")
    o.append("};")
    # A/B molotov with voice language Polish was 'played' but silent: `say` resolves the stream in the ACTIVE voice language; one flag per record per language
    langs = []
    for fn in ["english.psarc"] + [x for x in sorted(os.listdir(sd)) if x.endswith(".psarc") and x != "english.psarc"]:
        lang = os.path.splitext(fn)[0]
        have = eng if lang == "english" else psarc_names(os.path.join(sd, fn))
        vals = []
        for r in recs:
            e = idx.get(r["speech"])
            vals.append(1 if e and e[0] in have else 0)
        langs.append((lang, vals))
        o.append("static const uint8_t VXB_AVAIL_%s[] = {%s};" % (lang.upper(), ",".join(map(str, vals))))
    o.append("static const struct { const char *name; const uint8_t *tab; } VXB_LANGS[] = {")
    for lang, _ in langs:
        o.append('    {"%s", VXB_AVAIL_%s},' % (lang, lang.upper()))
    o.append("};")
    open(BHEADER, "w", newline="\n").write("\n".join(o) + "\n")
    for lang, vals in langs: print("  %s: %d of %d burn takes have a stream" % (lang, sum(vals), len(vals)))
    print(f"burn: {len(recs)} records -> {BDATA}, {BHEADER}")


def burn_records():
    return [(r["id"], r["speech"]) for r in json.load(open(BDATA))]


# ------------------------------------------------------------------------------------------------ execution begging
# A gun-execution victim begs with his OWN voice set (engine speech path: `say` on the victim's character = 3D, lip-sync, voice bus, the active voice
# language): kind 0 = an adrenaline plea (WLF: last-words-plead-sp "No, please--!"; Seraphites have no plea: the "No, no!" / "No!!" / "Oh no!!" shouts of
# take-cvr-solo-spj / see-cmbt-kill-cpr), kinds 1 / 2 / 3 = the bullet-hit grunts hit-by-pistol / -rifle / -shtgn (the first BEG_PAIN takes of the voice).
# Per language (every speech1/*.psarc) one flag per record = the stream exists there (a missing one would be played from English: skipped at runtime).
BEGDATA = os.path.join(HERE, "data", "vox_beg.json")
BEGHEADER = os.path.join(ROOT, "tools", "ext", "vox_beg.h")
INTPCM = os.path.join(ROOT, "tools", "ext", "vox_beg_int.pcm")
import zlib
sys.path.insert(0, HERE)
import int_vox_gen as IVG
BEG_CATS = {1: [("gen-enmy-cmbt-enmy-last-words-plead-sp", None)],
            0: [("gen-enmy-cmbt-enmy-take-cvr-solo-spj", re.compile(r"^(No, no!|No!|Don't!)$")), ("gen-enmy-see-cmbt-kill-cpr", re.compile(r"^(No!!|Oh no!!|No, no!!)$"))]}
# kinds 4-7 = the dismemberment scream chain (exec_beg.c, the shotgun leg shot): 4 hit-by-explsn (the long agony scream, 2-2.6 s), 5 fight-take-hvy (rapid
# short screams), 6 death-whine-lrg (the crying that follows), 7 brth-fight-injrd (injured panting between); VXG_DUR = the take's voiced length in ms
BEG_PAIN = 6
BEG_PAINCATS = ["eff-gen-hit-by-pistol", "eff-gen-hit-by-rifle", "eff-gen-hit-by-shtgn", "eff-gen-hit-by-explsn", "eff-gen-fight-take-hvy", "eff-gen-death-whine-lrg", "eff-gen-brth-fight-injrd"]
BEG_COUNT = [0, 6, 6, 6, 4, 4, 3, 3]
BEG_NKIND = 17
# INTERROGATION lines (tools/ext/interrogation.c): kind 8 = the interrogator's demand, kind 9 = the held victim's plea / answer. Real TLOU2 enemy takes, per faction:
# [fac index 0 Seraphite / 1 WLF] -> [(category, text regex)]; same order = pool order (the demands lead with the short "Where?!" takes).
BEG_INT = {
    # fist interrogation: 8 = the calm-threatening first demand, 10 = the aggressive demand on the slam; shiv interrogation: 13 = one calm demand
    8: {0: [("gen-enmy-prst-trgt-gone-plrl-solo-sp", re.compile(r"^Where are they\?!$"))],
        1: [("gen-enmy-prst-trgt-gone-plrl-solo-sp", re.compile(r"^Where are they\?!$"))]},
    10: {0: [("gen-enmy-spot-plyr-qstn-pr", re.compile(r"^Where\?!$"))],
         1: [("gen-enmy-spot-plyr-qstn-pr", re.compile(r"^Where\?!$"))]},
    13: {0: [],      # (no Seraphite "Talk to me." take: intvox.c uses the calm "Where are they?!" until an equivalent is approved)
         1: [("gen-enmy-srch-reinforcement-unwr-qstn-sp", re.compile(r"^Talk to me\.$"))]},
    # the held victim: 9 = the first (softer) answer, 11 = the desperate answer after the slam (and the shiv's one answer), 12 = Seraphite "Damned Wolf..." (only against a WLF interrogator)
    9: {0: [("gen-enmy-cmbt-mtshld-grbbed-scared-sp", re.compile(r"^(No\.\.\. no\.\.\.|Don't\.\.\. just\.\.\. wait\.\.\.)$"))],
        1: [("gen-enmy-cmbt-mtshld-grbbed-scared-sp", re.compile(r"^\{struggling efforts\} (Please\.\.\. oh god\.\.\. please\.|Please\.\.\. please\.\.\.|All right\.\.\. all right, jus)"))]},
    11: {0: [("gen-enmy-cmbt-mtshld-grbbed-scared-sp", re.compile(r"^(You'll regret this\.\.\.|Don't do this\.\.\.)$"))],
         1: [("gen-enmy-cmbt-mtshld-grbbed-scared-sp", re.compile(r"^\{struggling efforts\} Don't\.\.\. please\.\.\. don't\.\.\.")),
             ("gen-enmy-cmbt-mtshld-see-ally-klld-spj", re.compile(r"^\{struggling efforts\} (Wait, just\.\.\. wait!|Please don't!)$"))]},
    12: {0: [("gen-enmy-cmbt-mtshld-grbbed-scared-sp", re.compile(r"^Damned Wolf\.\.\.$"))], 1: []}}


def gen_beg():
    sd = os.path.join(GAME, "build", "pc", "main", "speech1")
    idx = json.load(open(os.path.join(sd, "english.xvag-index.json")))
    texts = all_texts(idx)
    eng = psarc_names(os.path.join(sd, "english.psarc"))
    others = [psarc_names(os.path.join(sd, x)) for x in sorted(os.listdir(sd)) if x.endswith(".psarc") and x != "english.psarc"]
    def cover(k):      # in how many other voice languages the take has a stream (grunts: the localisation recorded only some)
        e = idx.get(k)
        return sum(1 for h in others if e and e[0] in h)
    recs = []
    int_missing = []
    for fi, fac in enumerate(FACTIONS):
        for g in "mf":
            for v in VOICES:
                pre = "%s%s%s" % (fac, g, v)
                for kind in range(BEG_NKIND):
                    if kind == 0:
                        keys = []
                        for cat, rx in BEG_CATS[fi]:
                            keys += [k for k in sorted(idx) if re.match(r"^%s-%s-\d+$" % (re.escape(pre), re.escape(cat)), k) and (rx is None or rx.match(texts.get(k, "").strip()))]
                    elif kind >= 8:      # the interrogation slots (int_vox_gen.py SLOTS: which take plays in which beat; tail / trim / align modes)
                        metas = IVG.keys_for(kind, fi, pre, idx, texts, eng, int_missing)
                        keys = [m[0] for m in metas]
                    else:
                        keys = sorted((k for k in idx if re.match(r"^%s-%s-\d+$" % (re.escape(pre), re.escape(BEG_PAINCATS[kind - 1])), k) and idx[k][0] in eng), key=lambda k: (-cover(k), k))[:BEG_COUNT[kind]]
                    for n, k in enumerate(keys, 1):
                        r = {"fac": fac, "g": g, "v": v, "kind": kind, "n": n, "speech": k, "text": texts.get(k, ""), "id": "t2r-vox-beg-%s-%d-%02d" % (pre, kind, n)}
                        if kind >= 8:
                            r["mode"], r["flag"], r["pre"] = metas[n - 1][1], metas[n - 1][2], metas[n - 1][3]
                            if r["mode"]: r["text"] = {"tail": "Where are they? (tail of: %s)", "trim": "%s (trimmed)", "align": "%s", "full": "%s", "pre+tail": "%s + where are they?", "pre+full": "%s + Where are they?!"}[r["mode"]] % r["text"] if r["mode"] != "pre+tail" else "%s + where are they?" % texts.get(r["pre"], "")
                        recs.append(r)
    import speech_dur, tempfile
    int_ev = []
    arc = speech_dur.Psarc(os.path.join(sd, "english.psarc"))
    old = {r["id"]: r.get("dur") for r in json.load(open(BEGDATA))} if os.path.exists(BEGDATA) else {}
    with tempfile.TemporaryDirectory() as tmp:
        blob = bytearray()
        clips = {}      # (mode, speech, prefix) -> pcm entry: a take in two pools (e.g. "No, please--!" in the slam answers and the shiv answers) is stored once
        for r in recs:
            r["dur"] = old.get(r["id"]) or speech_dur.active_ms(arc, idx[r["speech"]][0], tmp)
            r["align"] = 0
            if r["kind"] >= 8 and r.get("mode") in ("tail", "pre+tail", "pre+full", "trim", "full", "align"):
                ck = (r["mode"], r["speech"], r.get("pre"))
                if ck in clips:
                    r["pcm"] = list(clips[ck]); r["dur"] = int(r["pcm"][1] * 1000 / r["pcm"][2])
                    int_ev.append("%s: shares the clip of an earlier record" % r["id"])
                    continue
                clip, ev = IVG.pcm_for(r["mode"], arc, idx, r["speech"], r.get("pre"), tmp, speech_dur.vgm(), None)
                prate = IVG.FULL_RATE if r["mode"] in ("full", "align", "pre+full") else 24000
                r["pcm"] = [len(blob) // 2, len(clip), prate]
                clips[ck] = tuple(r["pcm"])
                blob += clip.tobytes()
                r["dur"] = int(len(clip) * 1000 / prate)
                int_ev.append("%s: %s" % (r["id"], ev))
                if r["mode"] == "align":
                    r["align"] = int(round(IVG.align_full(arc, idx, r["speech"], tmp, speech_dur.vgm())))
                    int_ev.append("%s: last word starts at %s ms of the %d ms clip" % (r["id"], r["align"], r["dur"]))
        open(INTPCM, "wb").write(bytes(blob))
    json.dump(recs, open(BEGDATA, "w"), indent=1)
    langs = []
    for fn in ["english.psarc"] + [x for x in sorted(os.listdir(sd)) if x.endswith(".psarc") and x != "english.psarc"]:
        lang = os.path.splitext(fn)[0]
        have = eng if lang == "english" else psarc_names(os.path.join(sd, fn))
        vals = []
        for r in recs:
            e = idx.get(r["speech"])
            ok = bool(e) and (e[0] in have if lang == "english" else (e[0] not in eng or e[0] in have))
            vals.append(1 if ok else 0)
        langs.append((lang, vals))
    o = ["// GENERATED by tools/features/vox_lines.py genbeg - do not edit. Execution begging (t2r-ext exec_beg.c): vox-info records of the mod's greenlight module",
         "// (dc_data_patches.patch_vox_beg), played through `say` on the victim's character. VXG_RANGE[faction 0 Seraphite / 1 WLF][gender 0 male / 1 female][voice a..d][kind]",
         "// = {first, count} in VXG_LINES; kind 0 plea, 1 pistol / 2 rifle / 3 shotgun hit grunt, 4-7 dismemberment scream chain (see BEG_PAINCATS), 8 / 10 / 13 interrogator demands (calm fist / aggressive fist / calm shiv), 9 / 11 / 12 interrogated victim answers (BEG_INT). VXG_AVAIL_<LANG>[i] = 1 when record i has a stream in that voice language.",
         "static const uint64_t VXG_LINES[] = {"]
    rng = {}
    for i, r in enumerate(recs):
        key = (FACTIONS.index(r["fac"]), "mf".index(r["g"]), VOICES.index(r["v"]), r["kind"])
        f, c = rng.get(key, (i, 0))
        rng[key] = (f, c + 1)
        o.append("    0x%016xULL,   // %s <- %s %s" % (fnv(r["id"]), r["id"], r["speech"], r["text"].replace("*/", "").replace("\n", " ")))
    o.append("};")
    o.append("static const uint16_t VXG_DUR[] = {%s};" % ",".join(str(r["dur"]) for r in recs))
    o.append("// interrogation (int_vox_gen.py): VXG_PCM[i] = {first sample, samples, rate} of a record played from vox_beg_int.pcm instead of `say` (the tail of a take, a take with a prefix, a trimmed take; n 0 = say),")
    o.append("// VXG_ALIGN[i] = ms from the stream start to the onset of the take's last word (the head smash of \"You fuckin' bitch!\"), VXG_FLAG[i] bit 0 = \"Fuck you!\" (first OR second line, never both)")
    o.append("static const struct { uint32_t off, n; uint16_t rate; } VXG_PCM[] = {%s};" % ",".join("{%d,%d,%d}" % tuple(r.get("pcm", [0, 0, 24000])) for r in recs))
    o.append("static const uint16_t VXG_ALIGN[] = {%s};" % ",".join(str(r.get("align", 0)) for r in recs))
    o.append("// VXG_SRC[i] = crc32 of the source take (two records of one take - e.g. \"Release me.\" in the first and second line pools - are never both used in one interrogation)")
    o.append("static const uint32_t VXG_SRC[] = {%s};" % ",".join(str(zlib.crc32((r["speech"] + (r.get("pre") or "")).encode())) for r in recs))
    o.append("static const uint8_t VXG_FLAG[] = {%s};" % ",".join(str(r.get("flag", 0)) for r in recs))
    # The interrogation lines' text identity - VXG_TXT[i] = crc32 of the normalised subtitle text (one value for every voice of a line: intvox.c's no-repeat history across the
    # interrogations of a match), VXG_STR[i] = the text for the 'int vox: pick' log (kinds >= 8 only, "" otherwise)
    def _itxt(r):
        return re.sub(r"[^ -~]|[\\\"]", "", IVG.norm(texts.get(r["speech"], ""))) if r["kind"] >= 8 else ""
    o.append("static const uint32_t VXG_TXT[] = {%s};" % ",".join(str(zlib.crc32(_itxt(r).encode())) if r["kind"] >= 8 else "0" for r in recs))
    o.append("static const char *const VXG_STR[] = {%s};" % ",".join('"%s"' % _itxt(r) for r in recs))
    # A plea record that is a long panicked shout (text with '!!') - exec_beg.c drops them from the plea pools
    o.append("// VXG_SCREAM[i] = 1 for a plea record that is a long panicked shout (text with '!!': \"No!!\" / \"No, no!!\" / \"Oh no!!\", up to 1.7 s) - exec_beg.c drops them")
    o.append("static const uint8_t VXG_SCREAM[] = {%s};" % ",".join("1" if (r["kind"] == 0 and "!!" in r["text"]) else "0" for r in recs))
    o.append("static const uint16_t VXG_RANGE[2][2][4][%d][2] = {" % BEG_NKIND)
    for f in range(2):
        o.append("  {")
        for g in range(2):
            o.append("    {%s}," % ", ".join("{%s}" % ", ".join("{%d, %d}" % rng.get((f, g, v, k), (0, 0)) for k in range(BEG_NKIND)) for v in range(4)))
        o.append("  },")
    o.append("};")
    for lang, vals in langs:
        o.append("static const uint8_t VXG_AVAIL_%s[] = {%s};" % (lang.upper(), ",".join(map(str, vals))))
    o.append("static const struct { const char *name; const uint8_t *tab; } VXG_LANGS[] = {")
    for lang, _ in langs:
        o.append('    {"%s", VXG_AVAIL_%s},' % (lang, lang.upper()))
    o.append("};")
    open(BEGHEADER, "w", newline="\n").write("\n".join(o) + "\n")
    open(os.path.join(ROOT, "tools", "ext", "vox_beg_keys.h"), "w", newline="\n").write(
        "// GENERATED (probe table): fnv64 of each vox_beg record's speech stream key, same order as VXG_LINES (intvox.c t2r-ivx-probe.txt route a)\n"
        "static const uint64_t VXG_KEY[] = {%s};\n" % ",".join("0x%016xULL" % fnv(r["speech"]) for r in recs))
    print("beg: %d records -> %s, %s (+ %s)" % (len(recs), BEGDATA, BEGHEADER, INTPCM))
    print("interrogation slots - missing takes: %s" % (sorted(set(int_missing)) or "none"))
    for e in int_ev: print("  " + e)
    for lang, vals in langs:
        print("  %s: %d of %d records have a stream" % (lang, sum(vals), len(vals)))


def beg_records():
    return [(r["id"], r["speech"]) for r in json.load(open(BEGDATA))]


# ------------------------------------------------------------------------------------------------ downed groans
# A downed body groans with its OWN voice set (engine speech path: `say` on the body = 3D, the voice bus, the active voice language): kind 0 = the
# bleed-out groans of a dying NPC (<voice>-eff-gen-death-bleed-out-NNN) while lying, kind 1 = injured breaths (<voice>-eff-gen-brth-fight-injrd-NNN,
# the first DN_COUNT with a stream) while crawling. Only takes with a stream in english.psarc are records.
DNDATA = os.path.join(HERE, "data", "vox_downed.json")
DNHEADER = os.path.join(ROOT, "tools", "ext", "vox_downed.h")
DN_CATS = ["eff-gen-death-bleed-out", "eff-gen-brth-fight-injrd", "eff-gen-death-hdsht"]   # 2: SP's headshot death take (played at a death by a headshot)
DN_COUNT = [8, 6, 8]


def gen_downed():
    sd = os.path.join(GAME, "build", "pc", "main", "speech1")
    idx = json.load(open(os.path.join(sd, "english.xvag-index.json")))
    eng = psarc_names(os.path.join(sd, "english.psarc"))
    recs = []
    for fac in FACTIONS:
        for g in "mf":
            for v in VOICES:
                pre = "%s%s%s" % (fac, g, v)
                for kind, cat in enumerate(DN_CATS):
                    keys = sorted(k for k in idx if re.match(r"^%s-%s-\d+$" % (re.escape(pre), re.escape(cat)), k) and idx[k][0] in eng)[:DN_COUNT[kind]]
                    for n, k in enumerate(keys, 1):
                        recs.append({"fac": fac, "g": g, "v": v, "kind": kind, "n": n, "speech": k, "id": "t2r-vox-dn-%s-%d-%02d" % (pre, kind, n)})
    json.dump(recs, open(DNDATA, "w"), indent=1)
    o = ["// GENERATED by tools/features/vox_lines.py gendowned - do not edit. Downed groans (t2r-ext downed_vox.c): vox-info records of the mod's greenlight",
         "// module (dc_data_patches.patch_vox_downed), played through `say` on the downed body. VXD_RANGE[faction 0 Seraphite / 1 WLF][gender 0 male / 1 female]",
         "// [voice a..d][kind 0 bleed-out groan / 1 injured breath / 2 headshot death] = {first, count} in VXD_LINES (count 0: that voice has no such take).",
         "static const uint64_t VXD_LINES[] = {"]
    rng = {}
    for i, r in enumerate(recs):
        key = (FACTIONS.index(r["fac"]), "mf".index(r["g"]), VOICES.index(r["v"]), r["kind"])
        f, c = rng.get(key, (i, 0))
        rng[key] = (f, c + 1)
        o.append("    0x%016xULL,   // %s <- %s" % (fnv(r["id"]), r["id"], r["speech"]))
    o.append("};")
    o.append("static const uint16_t VXD_RANGE[2][2][4][3][2] = {")
    for f in range(2):
        o.append("  {")
        for g in range(2):
            o.append("    {%s}," % ", ".join("{%s}" % ", ".join("{%d, %d}" % rng.get((f, g, v, k), (0, 0)) for k in range(3)) for v in range(4)))
        o.append("  },")
    o.append("};")
    open(DNHEADER, "w", newline="\n").write("\n".join(o) + "\n")
    print("downed: %d records -> %s, %s" % (len(recs), DNDATA, DNHEADER))


def downed_records():
    return [(r["id"], r["speech"]) for r in json.load(open(DNDATA))]


# ------------------------------------------------------------------------------------------------ faction pick voice
# CHOOSE YOUR SIDE (tools/ext/choose.c): focusing a camp plays ONE real TLOU2 enemy take of that faction through the engine's own `say` (the active voice
# language, no subtitle, so it follows the language). Each take = one stream suffix, one record per voice
# set (militia / scar x male / female x a..d = 8 voices); a record without a stream in a language is flagged 0 there (a missing one would be played from
# English: skipped at runtime). REQUIRED takes: the Seraphite "No matter what... you're going to hell." and its WLF counterpart (the same
# defiant-last-words weight, WLF terms: "Doesn't matter how far you run... we'll find you...").
KEPT = os.path.join(ROOT, "re", "choose-1115", "vox_kept_user_1115.txt")


def pick_kept():
    """the (faction, take #, gender, voice) pairs the user kept in the audition (re/choose-1115/vox_kept_user_1115.txt, 'WLF: 02 text - female a'); None = no file (all)"""
    if not os.path.exists(KEPT):
        return None
    out = set()
    for ln in open(KEPT, encoding="utf-8"):
        m = re.match(r"^(WLF|Seraphites):\s*(\d+)\s.*-\s*(male|female)\s+([a-d])\s*$", ln.strip())
        if m:
            out.add(("mlt" if m.group(1) == "WLF" else "scr", int(m.group(2)), m.group(3)[0], m.group(4)))
    return out


PDATA = os.path.join(HERE, "data", "vox_pick.json")
PHEADER = os.path.join(ROOT, "tools", "ext", "vox_pick.h")
PICKS = {
    "scr": [("gen-enmy-cmbt-enmy-last-words-defiant-sp-007", 1), ("gam-sle-scar-village-logging-camp-enemy-convo-4-spj-004", 0),
            ("gam-fob-on-foot-defend-enemy-convo-3-pr-003", 0), ("gen-enmy-pryrs-confident-mod-sp-008", 0),
            ("gen-enmy-srch-start-rspns-confident-1x-sp-006", 0), ("gen-enmy-cmbt-callout-attack-plyr-cmd-plrl-cpr-009", 0)],
    "mlt": [("gam-afm-wlf-last-words-defiant-sp-001", 1), ("gam-afm-horse-chase-scar-wlf-fight-pr-003", 0), ("gam-afm-horse-chase-scar-wlf-fight-pr-006", 0),
            ("gam-afm-burning-village-callouts-pr-001", 0), ("gam-afm-brewery-gate-lifted-spj-005", 0), ("gen-enmy-cmbt-callout-attack-plyr-cmd-plrl-cpr-012", 0)],
}


def pick_ms(text):
    """a take's length from its subtitle (no stream decode here): ~62 ms a letter / space, 280 ms an ellipsis, 160 ms other pauses, + the attack"""
    t = re.sub(r"\{[^}]*\}", "", text)
    return int(300 + 62 * len(re.sub(r"[^A-Za-z' ]", "", t)) + 280 * t.count("...") + 160 * len(re.findall(r"[,.!?;]", t.replace("...", ""))))


def gen_pick():
    """(needs the game's speech1 archives + re/gamebin subtitles) -> data/vox_pick.json + ../ext/vox_pick.h"""
    sd = os.path.join(GAME, "build", "pc", "main", "speech1")
    idx = json.load(open(os.path.join(sd, "english.xvag-index.json")))
    texts = all_texts(idx)
    eng = psarc_names(os.path.join(sd, "english.psarc"))
    kept = pick_kept()
    recs, takes = [], []
    for fi, fac in enumerate(FACTIONS):
        for ti, (suffix, req) in enumerate(PICKS[fac]):
            if kept is not None and not any(k[0] == fac and k[1] == ti + 1 for k in kept):
                continue                                                  # a take the user deleted completely (WLF 1 / 5 / 6, Seraphites 6)
            text = None
            for g in "mf":
                for v in VOICES:
                    if kept is not None and (fac, ti + 1, g, v) not in kept:
                        continue                                          # a (line, voice) the user deleted in the audition
                    key = "%s%s%s-%s" % (fac, g, v, suffix)
                    if text is None and key in texts:
                        text = texts[key].strip()
                    if key not in idx or idx[key][0] not in eng:
                        print("  no english stream:", key)
                        continue
                    recs.append({"fac": fac, "take": ti, "req": req, "g": g, "v": v, "speech": key, "id": "t2r-vox-pick-%s-%02d-%s%s" % (fac, ti + 1, g, v)})
            assert text, suffix
            takes.append({"fac": fac, "take": ti, "req": req, "suffix": suffix, "text": text, "ms": pick_ms(text)})
    order = {}
    for t in takes:                                                       # take numbers = positions among the KEPT takes of the faction (0-based, the original order)
        order[(t["fac"], t["take"])] = sum(1 for u in takes if u["fac"] == t["fac"] and u["take"] < t["take"])
    for t in takes:
        t["take"] = order[(t["fac"], t["take"])]
    for r in recs:
        r["take"] = order[(r["fac"], r["take"])]
        r["id"] = "t2r-vox-pick-%s-%02d-%s%s" % (r["fac"], r["take"] + 1, r["g"], r["v"])
    json.dump({"takes": takes, "records": recs}, open(PDATA, "w"), indent=1)
    o = ["// GENERATED by tools/features/vox_lines.py genpick - do not edit. CHOOSE YOUR SIDE voice (tools/ext/choose.c): real TLOU2 enemy takes of each faction, played",
         "// through `say` in the active voice language. VXP_REC[i] = {fnv64 id of a vox-info record (dc_data_patches.patch_vox_pick), faction (0 Seraphite / 1 WLF),",
         "// take, gender (0 male / 1 female), voice a..d, REQUIRED}; VXP_TAKE[faction][take] = {text, length ms (estimated from the text), REQUIRED};",
         "// VXP_AVAIL_<LANG>[i] = the record's stream exists in speech1/<language>.psarc.",
         "typedef struct { uint64_t id; uint8_t fac, take, g, v, req; } vxp_rec_t;",
         "static const vxp_rec_t VXP_REC[] = {"]
    for r in recs:
        o.append("    {0x%016xULL, %d, %d, %d, %d, %d},   // %s <- %s" % (fnv(r["id"]), FACTIONS.index(r["fac"]), r["take"], "mf".index(r["g"]), VOICES.index(r["v"]), r["req"], r["id"], r["speech"]))
    o.append("};")
    o.append("#define VXP_NREC %d" % len(recs))
    o.append("#define VXP_NTAKE %d" % max(sum(1 for t in takes if t["fac"] == f) for f in FACTIONS))
    o.append("static const struct { const char *text; uint16_t ms; uint8_t req; } VXP_TAKE[2][VXP_NTAKE] = {")
    for fac in FACTIONS:
        o.append("    {%s}," % ", ".join('{"%s", %d, %d}' % (t["text"].replace('"', "'"), t["ms"], t["req"]) for t in takes if t["fac"] == fac))
    o.append("};")
    o.append("static const uint8_t VXP_NTAKES[2] = {%s};" % ", ".join(str(sum(1 for t in takes if t["fac"] == f)) for f in FACTIONS))
    langs = []
    for fn in ["english.psarc"] + [x for x in sorted(os.listdir(sd)) if x.endswith(".psarc") and x != "english.psarc"]:
        lang = os.path.splitext(fn)[0]
        have = eng if lang == "english" else psarc_names(os.path.join(sd, fn))
        vals = [1 if (r["speech"] in idx and idx[r["speech"]][0] in have) else 0 for r in recs]
        langs.append((lang, vals))
        o.append("static const uint8_t VXP_AVAIL_%s[] = {%s};" % (lang.upper(), ",".join(map(str, vals))))
    o.append("static const struct { const char *name; const uint8_t *tab; } VXP_LANGS[] = {")
    for lang, _ in langs:
        o.append('    {"%s", VXP_AVAIL_%s},' % (lang, lang.upper()))
    o.append("};")
    open(PHEADER, "w", newline="\n").write("\n".join(o) + "\n")
    for t in takes:
        print("%s take %d%s  %5d ms  %s  (%s)" % (t["fac"], t["take"] + 1, " REQUIRED" if t["req"] else "", t["ms"], t["text"], t["suffix"]))
    for lang, vals in langs:
        print("  %s: %d of %d pick records have a stream" % (lang, sum(vals), len(vals)))
    print("pick: %d records -> %s, %s" % (len(recs), PDATA, PHEADER))


def pick_records():
    return [(r["id"], r["speech"]) for r in json.load(open(PDATA))["records"]]


if __name__ == "__main__":
    if sys.argv[1:] == ["genbeg"]:   # execution begging (needs the game)
        gen_beg()
    elif sys.argv[1:] == ["gendowned"]:   # downed groans (needs the game index only)
        gen_downed()
    elif sys.argv[1:] == ["genpick"]:   # CHOOSE YOUR SIDE voice takes (needs the game speech archives + re/gamebin)
        gen_pick()
    elif sys.argv[1:] == ["genburn"]:   # burning-death screams (needs the game index only)
        gen_burn()
    elif sys.argv[1:] == ["genavail"]:   # per-language audio availability -> ext/vox_avail.h (needs the game)
        gen_avail()
    elif sys.argv[1:] == ["hdr"]:     # rewrite only the header from data/vox_lines.json (no game needed)
        write_header(load())
    elif sys.argv[1:] == ["gen"]:
        gen()
    elif sys.argv[1:] == ["genx"]:   # only the kinds (reload / noammo / throwwarn), the others stay as committed
        gen(NOFEM_KINDS)
    elif sys.argv[1:] == ["genthrow"]:   # only the throw kinds, male then female
        gen(THROW_KINDS)
        gen_female(THROW_KINDS)
    elif sys.argv[1:] == ["genwin"]:   # only the fewleft / matchwon / rapid kinds, male then female
        gen(WIN_KINDS)
        gen_female(WIN_KINDS)
    elif sys.argv[1:] == ["genpull"]:   # only the bolt-pull kind, male then female
        gen(PULL_KINDS)
        gen_female(PULL_KINDS)
    elif sys.argv[1:] == ["genwhistle"]:   # the Seraphite whistle lines, male + female; the spoken lines stay as committed
        gen_whistles()
    elif sys.argv[1:] == ["genreload"]:   # the reload / noammo kinds in the female voices
        gen_female(RELOAD_KINDS)
    elif sys.argv[1:] == ["genk"]:   # only the killer-callout tails, the others stay as committed
        gen(KILLCALL_KINDS)
    elif sys.argv[1:] == ["genex"]:  # only the match-start exchange kinds, male, the others stay as committed
        gen(EXCH_KINDS)
    elif sys.argv[1:] == ["genfx"]:  # the same for the female voices
        gen_female(EXCH_KINDS)
    elif sys.argv[1:] == ["pairs"]:  # review list of the exchange pairs (statement / reply / comments per faction)
        print_pairs()
    elif sys.argv[1:] == ["genf"]:   # female voices (T2R_FEMALE): data/vox_lines_female.json + ext/vox_lines_female.h
        gen_female()
    elif sys.argv[1:] == ["hdrf"]:   # only the female header, from the json
        d = json.load(open(FDATA))
        write_female_header(d["lines"], d["effort"])
    else:
        print(__doc__)
