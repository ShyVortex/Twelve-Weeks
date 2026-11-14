"""Vocabulary of the clan A-Life (tools/clan_alife.py): places, goods, projects, injuries, groups, jobs, skills, weather - English and Polish side by side,
and the two renderers.

A lexeme is stored as a KEY in a message (never as words), so a stored line can be rendered in any language later, like tools/clan_story.py does.
Polish forms: places  (nom, gen, at, to, from)   goods / projects / injuries  (nom, gen, acc, ins).  Names of people are never declined: the Polish
templates use pronoun switches ({A?on|ona}, {D?jego|jej}) and past-tense endings ({A?ł|ła}, {AB?li|ły} = feminine plural only when all named are women).
Placeholders in a template:  {A} {B} {C} {D} names;  {A_he} {A_his} ... English pronouns;  {A_role} the role noun (nominative only);  {dest} {goal} {proj}
{inj} {grp} {job} {skill} {orig} {keep} {prog} {nd} {nd_after} {nd_ago} {nd_in} {sup} {need} {size} {n} ... variables (see expand_en / expand_pl).
"""
import re

import clan_story as CS                                  # noqa: F401  (CS.render handles the English pronouns)
import clan_story_data as D
import clan_story_pl as PLN

# ------------------------------------------------------------------ places: key -> (EN, PL nom, gen, at, to, from)
PLACES = {
    "W": {
        "pike": ("the Pike Place market", "targ Pike Place", "targu Pike Place", "na targu Pike Place", "na targ Pike Place", "z targu Pike Place"),
        "library": ("the old library", "stara biblioteka", "starej biblioteki", "w starej bibliotece", "do starej biblioteki", "ze starej biblioteki"),
        "ferry": ("the ferry terminal", "terminal promowy", "terminala promowego", "na terminalu promowym", "na terminal promowy", "z terminala promowego"),
        "caphill": ("Capitol Hill", "dzielnica Capitol Hill", "dzielnicy Capitol Hill", "w dzielnicy Capitol Hill", "do dzielnicy Capitol Hill", "z dzielnicy Capitol Hill"),
        "pharm": ("the Jackson Street pharmacy", "apteka przy Jackson Street", "apteki przy Jackson Street", "w aptece przy Jackson Street",
                  "do apteki przy Jackson Street", "z apteki przy Jackson Street"),
        "ware": ("the warehouse district", "dzielnica magazynów", "dzielnicy magazynów", "w dzielnicy magazynów", "do dzielnicy magazynów", "z dzielnicy magazynów"),
        "clinic": ("the old clinic", "stara przychodnia", "starej przychodni", "w starej przychodni", "do starej przychodni", "ze starej przychodni"),
        "rail": ("the rail yard", "bocznica kolejowa", "bocznicy kolejowej", "na bocznicy kolejowej", "na bocznicę kolejową", "z bocznicy kolejowej"),
        "docks": ("the harbor docks", "nabrzeże", "nabrzeża", "na nabrzeżu", "na nabrzeże", "z nabrzeża"),
        "depot": ("the bus depot", "zajezdnia autobusowa", "zajezdni autobusowej", "w zajezdni autobusowej", "do zajezdni autobusowej", "z zajezdni autobusowej"),
        "subway": ("the flooded subway", "zalane metro", "zalanego metra", "w zalanym metrze", "do zalanego metra", "z zalanego metra"),
        "elec": ("the electronics store", "sklep elektroniczny", "sklepu elektronicznego", "w sklepie elektronicznym", "do sklepu elektronicznego", "ze sklepu elektronicznego"),
        "school": ("the high school", "liceum", "liceum", "w liceum", "do liceum", "z liceum"),
        "mall": ("the burned-out mall", "spalone centrum handlowe", "spalonego centrum handlowego", "w spalonym centrum handlowym",
                 "do spalonego centrum handlowego", "ze spalonego centrum handlowego"),
    },
    "S": {
        "shore": ("the mainland shore", "brzeg lądu", "brzegu lądu", "na brzegu lądu", "na brzeg lądu", "z brzegu lądu"),
        "pier": ("the drowned pier", "zatopione molo", "zatopionego mola", "przy zatopionym molo", "na zatopione molo", "z zatopionego mola"),
        "wreck": ("the ferry wreck", "wrak promu", "wraku promu", "przy wraku promu", "do wraku promu", "od wraku promu"),
        "orchard": ("the orchard hill", "wzgórze z sadem", "wzgórza z sadem", "na wzgórzu z sadem", "na wzgórze z sadem", "ze wzgórza z sadem"),
        "cannery": ("the old cannery", "dawna przetwórnia ryb", "dawnej przetwórni ryb", "w dawnej przetwórni ryb", "do dawnej przetwórni ryb", "z dawnej przetwórni ryb"),
        "quarry": ("the quarry road", "droga do kamieniołomu", "drogi do kamieniołomu", "na drodze do kamieniołomu", "na drogę do kamieniołomu", "z drogi do kamieniołomu"),
        "light": ("the lighthouse point", "przylądek z latarnią", "przylądka z latarnią", "na przylądku z latarnią", "na przylądek z latarnią", "z przylądka z latarnią"),
        "kelp": ("the kelp beds", "łąka wodorostów", "łąki wodorostów", "na łące wodorostów", "na łąkę wodorostów", "z łąki wodorostów"),
        "boathouse": ("the sunken boathouse", "zatopiona szopa na łodzie", "zatopionej szopy na łodzie", "przy zatopionej szopie na łodzie",
                      "do zatopionej szopy na łodzie", "od zatopionej szopy na łodzie"),
        "farm": ("the abandoned farmhouse", "opuszczone gospodarstwo", "opuszczonego gospodarstwa", "w opuszczonym gospodarstwie",
                 "do opuszczonego gospodarstwa", "z opuszczonego gospodarstwa"),
        "bridge": ("the fallen bridge", "zawalony most", "zawalonego mostu", "przy zawalonym moście", "do zawalonego mostu", "od zawalonego mostu"),
        "chapel": ("the burned chapel", "spalona kaplica", "spalonej kaplicy", "w spalonej kaplicy", "do spalonej kaplicy", "ze spalonej kaplicy"),
    },
}
PLACE_FORMS = ("", "_gen", "_at", "_to", "_from")

# ------------------------------------------------------------------ goods an expedition goes for: key -> (scope, EN, PL nom, gen, acc, ins)
GOODS = {
    "antibiotics": ("*", "antibiotics", "antybiotyki", "antybiotyków", "antybiotyki", "antybiotykami"),
    "cans": ("*", "canned food", "konserwy", "konserw", "konserwy", "konserwami"),
    "fuel": ("W", "fuel", "paliwo", "paliwa", "paliwo", "paliwem"),
    "bandages": ("*", "bandages and alcohol", "bandaże i spirytus", "bandaży i spirytusu", "bandaże i spirytus", "bandażami i spirytusem"),
    "batteries": ("W", "batteries", "baterie", "baterii", "baterie", "bateriami"),
    "ammo": ("W", "ammunition", "amunicja", "amunicji", "amunicję", "amunicją"),
    "seeds": ("*", "seeds", "nasiona", "nasion", "nasiona", "nasionami"),
    "clothes": ("*", "warm clothes", "ciepłe ubrania", "ciepłych ubrań", "ciepłe ubrania", "ciepłymi ubraniami"),
    "scrap": ("*", "scrap metal", "złom", "złomu", "złom", "złomem"),
    "filters": ("W", "water filters", "filtry do wody", "filtrów do wody", "filtry do wody", "filtrami do wody"),
    "rope": ("*", "rope", "lina", "liny", "linę", "liną"),
    "books": ("*", "books", "książki", "książek", "książki", "książkami"),
    "salt": ("*", "salt", "sól", "soli", "sól", "solą"),
    "parts": ("W", "spare parts", "części zamienne", "części zamiennych", "części zamienne", "częściami zamiennymi"),
    "arrowheads": ("S", "arrowheads", "groty strzał", "grotów strzał", "groty strzał", "grotami strzał"),
    "oil": ("S", "lamp oil", "olej lampowy", "oleju lampowego", "olej lampowy", "olejem lampowym"),
    "thread": ("S", "thread and needles", "nici i igły", "nici i igieł", "nici i igły", "nićmi i igłami"),
    "herbs": ("S", "medicinal herbs", "zioła lecznicze", "ziół leczniczych", "zioła lecznicze", "ziołami leczniczymi"),
}
NOUN_FORMS = ("", "_gen", "_acc", "_ins")
_ZE = re.compile(r"(?i)^(z|ż|ź|sk|sz|st|sp|śr|sm|sn|sw|wł|wz|w[^aeiouyąęó]|m[^aeiouyąęó])")


def with_prep(ins):
    """'z' / 'ze' + an instrumental form ('ze złomem', 'z solą')."""
    return ("ze " if _ZE.match(ins) else "z ") + ins

# ------------------------------------------------------------------ building projects: key -> (scope, EN, PL nom, gen, acc, ins)
PROJECTS = {
    "tower": ("W", "the watchtower", "wieża obserwacyjna", "wieży obserwacyjnej", "wieżę obserwacyjną", "wieżą obserwacyjną"),
    "rain": ("*", "the rain catchers", "łapacze deszczu", "łapaczy deszczu", "łapacze deszczu", "łapaczami deszczu"),
    "genshed": ("W", "the generator shed", "szopa z agregatem", "szopy z agregatem", "szopę z agregatem", "szopą z agregatem"),
    "greenhouse": ("*", "the greenhouse", "szklarnia", "szklarni", "szklarnię", "szklarnią"),
    "barricade": ("W", "the north barricade", "północna barykada", "północnej barykady", "północną barykadę", "północną barykadą"),
    "coop": ("*", "the chicken coop", "kurnik", "kurnika", "kurnik", "kurnikiem"),
    "filter": ("*", "the water filter", "filtr wody", "filtra wody", "filtr wody", "filtrem wody"),
    "sickbay": ("W", "the sick bay", "izba chorych", "izby chorych", "izbę chorych", "izbą chorych"),
    "mast": ("W", "the radio mast", "maszt radiowy", "masztu radiowego", "maszt radiowy", "masztem radiowym"),
    "palisade": ("S", "the palisade", "palisada", "palisady", "palisadę", "palisadą"),
    "smokehouse": ("S", "the smokehouse", "wędzarnia", "wędzarni", "wędzarnię", "wędzarnią"),
    "terraces": ("S", "the orchard terraces", "tarasy w sadzie", "tarasów w sadzie", "tarasy w sadzie", "tarasami w sadzie"),
    "boathouse": ("S", "the new boathouse", "nowa szopa na łodzie", "nowej szopy na łodzie", "nową szopę na łodzie", "nową szopą na łodzie"),
    "beacon": ("S", "the beacon fire", "ogień sygnałowy", "ognia sygnałowego", "ogień sygnałowy", "ogniem sygnałowym"),
    "hall": ("S", "the healing hall", "sala uzdrowicieli", "sali uzdrowicieli", "salę uzdrowicieli", "salą uzdrowicieli"),
    "loom": ("S", "the great loom", "wielkie krosno", "wielkiego krosna", "wielkie krosno", "wielkim krosnem"),
}
PROG = {   # progress bucket -> (EN predicate of "the work on X is ...", PL predicate of "Prace nad X ...")
    0: ("barely started", "dopiero ruszyły"), 1: ("about a third done", "są mniej więcej w jednej trzeciej"),
    2: ("about half done", "są mniej więcej w połowie"), 3: ("nearly done", "dobiegają końca")}

# ------------------------------------------------------------------ injuries (healthy people: they work light duty, they are NOT counted as sick): key -> (EN, nom, gen, acc, ins)
INJURIES = {
    "ankle": ("a sprained ankle", "skręcona kostka", "skręconej kostki", "skręconą kostkę", "skręconą kostką"),
    "hand": ("a cut hand", "rozcięta dłoń", "rozciętej dłoni", "rozciętą dłoń", "rozciętą dłonią"),
    "ribs": ("bruised ribs", "stłuczone żebra", "stłuczonych żeber", "stłuczone żebra", "stłuczonymi żebrami"),
    "burn": ("a burned hand", "poparzona dłoń", "poparzonej dłoni", "poparzoną dłoń", "poparzoną dłonią"),
    "back": ("a sore back", "bolące plecy", "bolących pleców", "bolące plecy", "bolącymi plecami"),
    "eye": ("a black eye", "podbite oko", "podbitego oka", "podbite oko", "podbitym okiem"),
    "knee": ("a bad knee", "obolałe kolano", "obolałego kolana", "obolałe kolano", "obolałym kolanem"),
}

# ------------------------------------------------------------------ neighbours to trade with (always plural): key -> (scope, EN, PL nom, gen, acc, ins)
GROUPS = {
    "ferry": ("W", "the ferry traders", "handlarze z promu", "handlarzy z promu", "handlarzy z promu", "handlarzami z promu"),
    "scrap": ("W", "the scrappers from Capitol Hill", "szabrownicy z Capitol Hill", "szabrowników z Capitol Hill", "szabrowników z Capitol Hill",
              "szabrownikami z Capitol Hill"),
    "peddlers": ("W", "the Westlake peddlers", "handlarze z Westlake", "handlarzy z Westlake", "handlarzy z Westlake", "handlarzami z Westlake"),
    "fishers": ("*", "the dock fishermen", "rybacy z doków", "rybaków z doków", "rybaków z doków", "rybakami z doków"),
    "families": ("*", "two nomad families", "dwie rodziny koczowników", "dwóch rodzin koczowników", "dwie rodziny koczowników", "dwoma rodzinami koczowników"),
    "boats": ("S", "the boat traders from the mainland", "handlarze łodziowi z lądu", "handlarzy łodziowych z lądu", "handlarzy łodziowych z lądu",
              "handlarzami łodziowymi z lądu"),
    "shore": ("S", "the shore peddlers", "handlarze z wybrzeża", "handlarzy z wybrzeża", "handlarzy z wybrzeża", "handlarzami z wybrzeża"),
    "salt": ("S", "the wandering salt-sellers", "wędrowni sprzedawcy soli", "wędrownych sprzedawców soli", "wędrownych sprzedawców soli", "wędrownymi sprzedawcami soli"),
}

# ------------------------------------------------------------------ where a newcomer came from (the PL form carries its preposition): key -> (scope, EN, PL "from ...")
ORIGINS = {
    "apartments": ("W", "in a Capitol Hill apartment block", "w bloku na Capitol Hill"),
    "highway": ("W", "with a column of walkers on the highway", "z kolumną wędrowców na szosie"),
    "boat": ("*", "on a fishing boat in the bay", "na kutrze rybackim w zatoce"),
    "defector": ("W", "with the Scars", "wśród Blizn"),
    "quarantine": ("W", "in a quarantine zone that fell apart", "w strefie kwarantanny, która się rozpadła"),
    "farm": ("*", "on a farm outside the city", "na farmie za miastem"),
    "cellar": ("*", "in a cellar, hiding", "w piwnicy, w ukryciu"),
    "mainland": ("S", "with a family on the mainland", "z rodziną na lądzie"),
    "alone": ("S", "alone on the mainland", "samotnie na lądzie"),
    "wolves": ("S", "with the Wolves", "wśród Wilków"),
    "hills": ("S", "in the hills behind the shore", "we wzgórzach za brzegiem"),
}

# ------------------------------------------------------------------ pasts: key -> (scope, EN "{A} <verb phrase> before ...", PL with {A?..|..} switches)
JOBS = {
    "bus": ("W", "drove a city bus", "jeździ{A?ł|ła} miejskim autobusem"),
    "docks": ("*", "worked the docks", "pracowa{A?ł|ła} w porcie"),
    "nurse": ("*", "was a nurse", "pracowa{A?ł|ła} jako {A?pielęgniarz|pielęgniarka}"),
    "diner": ("W", "cooked at a diner", "gotowa{A?ł|ła} w barze"),
    "electric": ("W", "was an electrician", "pracowa{A?ł|ła} jako {A?elektryk|elektryczka}"),
    "teacher": ("*", "taught school", "uczy{A?ł|ła} w szkole"),
    "mail": ("W", "delivered the mail", "roznosi{A?ł|ła} pocztę"),
    "framer": ("*", "framed houses", "stawia{A?ł|ła} szkielety domów"),
    "medic": ("W", "was a paramedic", "pracowa{A?ł|ła} jako {A?ratownik|ratowniczka}"),
    "bike": ("W", "ran a bike repair shop", "prowadzi{A?ł|ła} warsztat rowerowy"),
    "deck": ("*", "was a ferry deckhand", "pracowa{A?ł|ła} na promie jako {A?marynarz|marynarka}"),
    "office": ("W", "cleaned offices downtown", "sprząta{A?ł|ła} biura w śródmieściu"),
    "fish": ("S", "fished the sound", "łowi{A?ł|ła} ryby w cieśninie"),
    "bees": ("S", "kept bees", "trzyma{A?ł|ła} pszczoły"),
    "nets": ("S", "wove fishing nets", "plot{A?ł|ła} sieci rybackie"),
    "goats": ("S", "raised goats", "hodowa{A?ł|ła} kozy"),
    "orchard": ("S", "tended an orchard", "opiekowa{A?ł|ła} się sadem"),
    "boats": ("S", "mended boats", "naprawia{A?ł|ła} łodzie"),
    "bread": ("S", "baked the bread", "piek{A?ł|ła} chleb"),
}

# ------------------------------------------------------------------ what a mentor teaches (an infinitive phrase): key -> (scope, EN, PL)
SKILLS = {
    "map": ("*", "read a map", "czytać mapy"), "knot": ("*", "tie a proper knot", "wiązać porządne węzły"), "patch": ("*", "patch a tire", "łatać opony"),
    "dress": ("*", "dress a wound", "opatrywać rany"), "aim": ("W", "hold a rifle steady", "pewnie trzymać karabin"), "fish": ("*", "gut a fish", "patroszyć ryby"),
    "listen": ("*", "tell a clicker from the sound it makes", "rozpoznawać klikacza po dźwięku"), "snare": ("*", "set a snare", "zastawiać sidła"),
    "solder": ("W", "solder a radio", "lutować radia"), "stitch": ("*", "stitch a cut", "zszywać rany"), "bow": ("S", "draw a bow without shaking", "naciągać łuk bez drżenia"),
    "weave": ("S", "weave a net", "pleść sieci"), "tide": ("S", "read the tides", "czytać pływy"), "count": ("*", "count stock honestly", "uczciwie liczyć zapasy"),
    "fire": ("*", "keep a fire alive in the rain", "podtrzymywać ogień w deszczu"),
}

# ------------------------------------------------------------------ keepsakes of the dead: key -> (EN, PL nom, gen, acc, ins)
KEEPS = {
    "cap": ("cap", "czapka", "czapki", "czapkę", "czapką"), "knife": ("knife", "nóż", "noża", "nóż", "nożem"),
    "harmonica": ("harmonica", "harmonijka", "harmonijki", "harmonijkę", "harmonijką"), "scarf": ("scarf", "szal", "szala", "szal", "szalem"),
    "notebook": ("notebook", "notes", "notesu", "notes", "notesem"), "mug": ("tin mug", "blaszany kubek", "blaszanego kubka", "blaszany kubek", "blaszanym kubkiem"),
    "boots": ("boots", "buty", "butów", "buty", "butami"), "watch": ("wristwatch", "zegarek", "zegarka", "zegarek", "zegarkiem"),
}

WEATHER = ("rain", "fog", "cold", "clear", "smoke", "wind")
SEASONS = (("late autumn", "późna jesień"), ("deep winter", "głęboka zima"), ("thin early spring", "chuda wczesna wiosna"))


def season_of(week):
    """12 weeks: 1-4 late autumn, 5-8 deep winter, 9-12 early spring."""
    return 0 if week <= 4 else 1 if week <= 8 else 2


def _fk_ok(scope, fk):
    return scope in ("*", fk)


def pool_keys(table, fk):
    """Keys of a (scope-first) lexicon table usable by faction fk, in a stable order."""
    return [k for k, v in table.items() if _fk_ok(v[0], fk)]


# ------------------------------------------------------------------ number phrases
_NUMS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _en_days(n):
    return "%s day%s" % (_NUMS[n] if 0 <= n <= 10 else n, "" if n == 1 else "s")


def _pl_days(n, kind):
    """kind: nom 'dwa dni', after 'po dwóch dniach', ago 'dwa dni temu', in 'za dwa dni'."""
    nom = {1: "jeden dzień", 2: "dwa dni", 3: "trzy dni", 4: "cztery dni", 5: "pięć dni", 6: "sześć dni", 7: "siedem dni"}.get(n, "%d dni" % n)
    if kind == "nom":
        return nom
    if kind == "after":
        return "po " + {1: "jednym dniu", 2: "dwóch dniach", 3: "trzech dniach", 4: "czterech dniach", 5: "pięciu dniach", 6: "sześciu dniach",
                        7: "siedmiu dniach"}.get(n, "%d dniach" % n)
    if kind == "ago":
        return nom + " temu" if n != 1 else "wczoraj"
    return "za " + nom


# ------------------------------------------------------------------ variables -> words
def expand_en(sym):
    fk = sym.get("f", "W")
    v = CS.expand_en({k: sym[k] for k in ("f", "day", "week", "inf", "ill") if k in sym})
    if "dest" in sym:
        v["dest"] = PLACES[fk][sym["dest"]][0]
    if "place" in sym:
        v["place"] = sym["place"]
    for key, table, idx in (("goal", GOODS, 1), ("proj", PROJECTS, 1), ("grp", GROUPS, 1), ("inj", INJURIES, 0), ("keep", KEEPS, 0)):
        if key in sym:
            v[key] = table[sym[key]][idx]
    if "job" in sym:
        v["job"] = JOBS[sym["job"]][1]
    if "skill" in sym:
        v["skill"] = SKILLS[sym["skill"]][1]
    if "orig" in sym:
        v["orig"] = ORIGINS[sym["orig"]][1]
    if "prog" in sym:
        v["prog"] = PROG[sym["prog"]][0]
    if "nd" in sym:
        n = int(sym["nd"])
        v.update(nd=_en_days(n), nd_after="after " + _en_days(n), nd_ago=("yesterday" if n == 1 else _en_days(n) + " ago"), nd_in="in " + _en_days(n))
    if "wx" in sym:
        v["wx"] = sym["wx"]
    if "season" in sym:
        v["season"] = SEASONS[sym["season"]][0]
    for k in ("sup", "need", "size", "sick_n", "hungry_n", "due", "jd", "n"):
        if k in sym:
            v[k] = sym[k]
    if "size" in sym:
        v["size_ppl"] = "%s people" % _NUMS[sym["size"]] if 0 < sym["size"] <= 10 else "%d people" % sym["size"]
    return v


def expand_pl(sym):
    fk = sym.get("f", "W")
    v = PLN.expand({k: sym[k] for k in ("f", "day", "week", "inf", "ill") if k in sym})
    if "dest" in sym:
        for suf, form in zip(PLACE_FORMS, PLACES[fk][sym["dest"]][1:]):
            v["dest" + suf] = form
    if "place" in sym:
        v["place"] = sym["place"]
    for key, table in (("goal", GOODS), ("proj", PROJECTS), ("grp", GROUPS)):
        if key in sym:
            for suf, form in zip(NOUN_FORMS, table[sym[key]][2:]):
                v[key + suf] = form
            v[key + "_with"] = with_prep(table[sym[key]][5])
            v[key + "_nom"] = table[sym[key]][2]
    if "inj" in sym:
        for suf, form in zip(NOUN_FORMS, INJURIES[sym["inj"]][1:]):
            v["inj" + suf] = form
        v["inj_with"] = with_prep(INJURIES[sym["inj"]][4])
        v["inj_nom"] = INJURIES[sym["inj"]][1]
    if "keep" in sym:
        for suf, form in zip(NOUN_FORMS, KEEPS[sym["keep"]][1:]):
            v["keep" + suf] = form
        v["keep_nom"] = KEEPS[sym["keep"]][1]
    if "job" in sym:
        v["job"] = JOBS[sym["job"]][2]
    if "skill" in sym:
        v["skill"] = SKILLS[sym["skill"]][2]
    if "orig" in sym:
        v["orig"] = ORIGINS[sym["orig"]][2]
    if "prog" in sym:
        v["prog"] = PROG[sym["prog"]][1]
    if "nd" in sym:
        n = int(sym["nd"])
        v.update(nd=_pl_days(n, "nom"), nd_after=_pl_days(n, "after"), nd_ago=_pl_days(n, "ago"), nd_in=_pl_days(n, "in"))
    if "season" in sym:
        v["season"] = SEASONS[sym["season"]][1]
    for k in ("sup", "need", "size", "sick_n", "hungry_n", "due", "jd", "n"):
        if k in sym:
            v[k] = sym[k]
    if "size" in sym:
        v["size_ppl"] = pl_people(int(sym["size"]))
    return v


def pl_people(n):
    """'5 osób', '3 osoby', '22 osoby'."""
    few = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    return "%d %s" % (n, "osoby" if few else "osób" if n != 1 else "osoba")


# ------------------------------------------------------------------ rendering
_KEY = re.compile(r"\{(\w+)\}")
_SW = re.compile(r"\{([A-D]+)\?([^|{}]*)\|([^|{}]*)\}")
_PERSON = re.compile(r"^([ABCD])_(\w+)$")


def role_word(person, fk, lang):
    r = person.get("r") or "scavenger"
    if lang == "pl":
        pair = PLN.ROLES[r][0 if fk == "W" else 1]
        return pair[1] if person.get("g") == "f" else pair[0]
    return D.ROLES[r][0 if fk == "W" else 1]


def render(tpl, people, vars_, lang="en", fk="W"):
    """Fill a template: variables first (their values may hold switches), then the {A?m|f} switches (PL), then names / pronouns / roles."""
    def var(m):
        k = m.group(1)
        if k in vars_:
            val = str(vars_[k])
            before = tpl[:m.start()].rstrip()
            if val[:1].islower() and (not before or before[-1] in ".!?\"'„”"):
                val = val[:1].upper() + val[1:]
            return val
        return m.group(0)
    s = _KEY.sub(var, tpl)

    def sw(m):
        fem = all(people[ch]["g"] == "f" for ch in m.group(1))
        return m.group(3) if fem else m.group(2)
    s = _SW.sub(sw, s)

    def person(m):
        k = m.group(1)
        pm = _PERSON.match(k)
        if pm:
            p = people[pm.group(1)]
            w = pm.group(2)
            if w == "role":
                return role_word(p, fk, lang)
            r = CS.PRON[p["g"]][w.lower()]
            return r[:1].upper() + r[1:] if w[:1].isupper() else r
        if k in people:
            return people[k]["n"]
        return m.group(0)
    return _KEY.sub(person, s)


def letters_of(tpl):
    out = set(re.findall(r"\{([A-D])(?:_\w+)?\}", tpl))
    for m in _SW.finditer(tpl):
        out |= set(m.group(1))
    return out


def vars_of(tpl):
    """Variable keys (not people) of a template."""
    return {k for k in _KEY.findall(tpl) if not re.fullmatch(r"[A-D](_\w+)?", k)}
