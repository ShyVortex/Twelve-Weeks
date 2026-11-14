"""Kids are never fighters: a clan member with role "kid" is never cast in combat lore - matches, kills, downs, executions, being shot or wounded in a
fight, raids / patrols / guard duty, dangerous scavenging, "fell in battle" deaths, revenge, weapon training as a fighter, battle scars, heroics on the line.
Allowed for kids: home life, chores, play, learning, trinkets and books, sickness / hunger, grief, being comforted, small help at camp.

Two layers keep this true in every clan module (story, A-Life, chronicle, saga, arcs, loot, perks):
  1. structure: the picks of combat scenes use can_fight(p) (people who are not kids), the death roll gives kids no combat cause;
  2. text: a template that reads as combat (combat_text) is never drawn when one of the people it names is a kid (kid_safe), in English and Polish.
When a kid grows up (the role changes to an adult role) can_fight is true again.
"""
import functools
import re

KID_ROLE = "kid"


def is_kid(p):
    return bool(p) and p.get("r") == KID_ROLE


def can_fight(p):
    """Who may be cast in combat, raid, patrol, guard or kill lore: everybody but kids (elders are the existing rule of each module)."""
    return not is_kid(p)


def fighters(people):
    return [p for p in people if can_fight(p)]


# structural tags: the pools / kinds that are combat by nature (a kid is never drawn into them, whatever the wording)
COMBAT_KINDS = {"death_attack", "death_attack_many", "death_bite", "death_bite_kin", "death_turned", "death_lost", "event_hold", "event_heavy", "event_massacre", "event_warn"}
COMBAT_POOLS_ALIFE = {"thr_enemy", "thr_inf", "thr_smoke", "thr_up", "thr_down", "thr_after", "exp_ret_contact", "exp_ret_inf", "exp_ret_hurt", "exp_lost", "exp_wait",
                      "exp_recall", "inj_mid", "inj_heal", "tr_rumor", "tr_meet", "proj_start", "proj_prog", "proj_stall", "proj_done"}
COMBAT_POOLS_CHRON = {"match_kills", "match_strong", "match_even", "match_bad", "match_downs", "raid_prep", "prep", "loot_found", "use_ammo", "haul_good", "haul_short"}
COMBAT_SCENES_SAGA = {"win", "loss", "down", "exec", "rev", "quiet", "haul", "prep", "use"}

# words that put a line in combat / raid / patrol / danger territory
_EN = (r"shot|shoot|shoots|shooting|gunfire|gun|guns|rifle|rifles|pistol|pistols|shotgun|revolver|bow|arrow|arrows|crossbow|bullet|bullets|ammo|ammunition|clips|cartridges?|"
       r"kill|kills|killed|killer|killing|slain|murder|murdered|fight|fights|fighter|fighters|fighting|fought|battle|battles|combat|war|warrior|soldier|soldiers|militia|"
       r"raid|raids|raider|raiders|raiding|patrol|patrols|patrolling|sentry|lookout|watchtower|on watch|first watch|night watch|guard duty|ambush|siege|skirmish|firefight|"
       r"downed|went down|goes down|knocked down|execute|executed|execution|executions|wound|wounds|wounded|stab|stabbed|blade|blades|machete|knife|knives|shiv|bomb|bombs|molotov|grenade|grenades|"
       r"enemy|enemies|scars|hostile|hostiles|revenge|avenge|avenged|vengeance|payback|hero|heroic|heroes|bravery|"
       r"scouting|scout out|scavenging|scavenge|scavenged|supply run|went out|goes out|gone out|sent out|out on the road|beyond the wall|beyond the fence|expedition|expeditions|"
       r"concussion|amputation|infected|clicker|clickers|runner|runners|stalker|stalkers|shambler|shamblers|bloater|bloaters|sniper|headshot|headshots|fell in|last stand|"
       r"sparring|weapon training|marksman|trigger|going foraging|went hunting|goes hunting|foraging|hunting party|stood watch|keeps watch|keeping watch|"
       r"watch schedule|watch rota|watch roster|watch duty|the night watch|hold the line|holds the line|held the line|front line|frontline|barricade|barricades|gate guard|armed|gas mask|mask filters?")
_PL = (r"strzel\w*|strzał\w*|karabin\w*|pistolet\w*|rewolwer\w*|śrutów\w*|łuk\w*|bełt\w*|kusz\w*|pocisk\w*|amunicj\w*|magazynek|magazynk\w*|nabój|naboj\w*|naboi|"
       r"zabij\w*|zabić|zabit\w*|zabił\w*|zabici\w*|zabój\w*|morder\w*|zginął\w*|zginęł\w*|poległ\w*|walk\w*|walcz\w*|bitw\w*|bój|boju|boje|wojn\w*|wojow\w*|żołnier\w*|"
       r"rajd\w*|wypad\w*|patrol\w*|wart\w*|warci\w*|czat\w*|zasadzk\w*|oblęż\w*|potyczk\w*|"
       r"powal\w*|obali\w*|egzekuc\w*|stracen\w*|rann\w*|rany|ranę|ranie|ran\b|rań|dźgn\w*|ostrz\w*|ostrze|maczet\w*|nóż|noża|noże|noży|bomb\w*|molotow\w*|granat\w*|"
       r"wróg|wroga|wrogi\w*|wrogów|blizn\w*|bliźni\w*|zemst\w*|pomści\w*|bohater\w*|odważ\w*|"
       r"zwiad\w*|zwiadow\w*|wyszed\w*|wyszła|wyszli|wyruszy\w*|wysłan\w*|poza murem|poza płotem|"
       r"zarażon\w*|klikacz\w*|biegacz\w*|stalker\w*|szambler\w*|bloater\w*|snajper\w*|strzał w głowę|ostatni\w* bastion|"
       r"ćwicz\w* (strzel|walk)|trening\w*|celn\w*|cel[ue]\b|celuj\w*|spust\w*|"
       r"poluj\w*|łow\w* (?:zwierz)|zbieractw\w* wypad|wyprawa|wyprawy|wypraw\w*|"
       r"barykad\w*|uzbroj\w*|zbro\w*|kamizelk\w*|maskę gazową|maski gazowej|filtr\w* do maski")
_VARS = {"enemy", "enemies", "enemy_gen", "enemy_ins", "wpn", "dn_p", "ex_p", "ex_t", "rv_p", "hs_p", "dt_p", "site", "cloth", "cause", "kills", "deaths", "downs",
         "ysite", "dsite", "dcloth", "inf", "infs", "inj", "ammo_n"}
COMBAT_RE = re.compile(r"(?<![\w'])(?:%s)(?![\w'])" % _EN, re.I)
COMBAT_RE_PL = re.compile(r"(?<!\w)(?:%s)(?!\w)" % _PL, re.I)
_KEY_RE = re.compile(r"\{(\w+?)(?:_\w+)?\}")
_LETTER_RE = re.compile(r"\{([ABCD])(?:_\w+)?\}")


_PL_LETTERS = re.compile("[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")


@functools.lru_cache(maxsize=None)
def combat_text(t, lang=None):
    """True when a template / sentence (with or without {placeholders}) reads as combat, raid, patrol, danger-scavenging or weapon lore.  lang "en" | "pl" picks the word
    list; None = Polish when the text has Polish letters, else English (callers that know the language say it)."""
    if not t:
        return False
    for k in _KEY_RE.findall(t):
        if k in _VARS:
            return True
    if lang is None:
        lang = "pl" if _PL_LETTERS.search(t) else "en"
    return bool((COMBAT_RE_PL if lang == "pl" else COMBAT_RE).search(t))


@functools.lru_cache(maxsize=None)
def _letters(tpl):
    return frozenset(_LETTER_RE.findall(tpl or ""))


def letters_in(tpl):
    return set(_letters(tpl))


def kid_letters(tpl, people):
    """The letters of `tpl` that stand for kids in `people` ({letter: person})."""
    return {L for L in letters_in(tpl) if is_kid(people.get(L))}


def kid_safe(tpl, people, *more):
    """False when any of the templates (the English one, its Polish twin ...) is combat while it names a kid."""
    ks = kid_letters(tpl, people)
    for m in more:
        ks |= kid_letters(m, people)
    if not ks:
        return True
    return not (combat_text(tpl, "en") or any(combat_text(m, "pl") for m in more if m))


def kid_text_ok(text, people, lang="en"):
    """False when a RENDERED line (variables filled in: an origin, a keepsake, a past) names a kid in a sentence that reads as combat."""
    ks = [p["n"] for p in people.values() if is_kid(p) and p.get("n")]
    if not ks or not combat_text(text, lang):
        return True
    for s_ in re.split(r"(?<=[.!?])\s+", text):
        if combat_text(s_, lang) and any(re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", s_) for n in ks):
            return False
    return True


def any_kid(people):
    return any(is_kid(p) for p in people.values())


def kid_names(st):
    """Names (alive or dead) of the kids of a clan story state; dead kids keep their role in st["dead"]."""
    return {p["n"] for p in st.get("people", []) if is_kid(p)} | {d["n"] for d in st.get("dead", []) if d.get("r") == KID_ROLE}
