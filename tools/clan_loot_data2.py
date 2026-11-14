"""Data of the clan loot model, part 2 (tools/clan_loot.py): per-map place kinds, micro-locations, conditions, story hooks.  English + Polish, no logic."""

# which place kinds each map has, strongest first (see clan_loot_data.ITEMS for the kind codes)
MAP_KINDS = {
    "Forest": ("wi", "ca", "hs"), "Gas Station": ("sh", "hw", "ra"), "School": ("sc", "hs", "of"), "Shipyard": ("ma", "ra", "hw"),
    "Resort": ("ht", "ma", "hs"), "Seraphite Camp": ("ca", "wi", "fa"), "Houses": ("hs", "fa", "sh"), "Hospital": ("ho", "ph", "of"),
    "Hardware Store": ("hw", "sh", "of"), "Motel": ("ht", "hs", "sh"), "Hillcrest": ("hs", "sh", "ho"), "TV Station": ("of", "sh", "ra"),
    "Train Station": ("ra", "hw", "sh"), "Downtown": ("sh", "of", "mi"), "Lodge": ("ht", "wi", "hs"), "Jackson Suburbs": ("hs", "fa", "sc"),
    "Suburbs": ("hs", "fa", "sh"), "Bookstore": ("sh", "of", "hs"), "Hillside": ("ph", "hs", "mi"), "Capitol Hill Shops": ("sh", "ph", "hs"),
    "Convention Center": ("mi", "of", "sh"), "Overpass": ("mi", "ra", "wi"),
}
GENERIC_KINDS = ("hs", "sh", "of")

# micro-locations per kind: (EN, PL) - adverbial phrases that follow the verb
MICRO = {
    "ph": [("behind the pharmacy counter", "za ladą apteki"), ("in the locked drug cabinet", "w zamkniętej szafce z lekami"),
           ("on the bottom shelf of the dispensary", "na dolnej półce w aptece"), ("in the back room of the pharmacy", "na zapleczu apteki"),
           ("under the prescription desk", "pod biurkiem z receptami")],
    "ho": [("in a nurse's station drawer", "w szufladzie dyżurki pielęgniarek"), ("on a supply cart left in the corridor", "na wózku z zaopatrzeniem w korytarzu"),
           ("behind a collapsed ceiling panel", "za zawalonym panelem sufitowym"), ("in the ward's medicine cabinet", "w szafce z lekami na oddziale"),
           ("in a sealed crash cart", "w zamkniętym wózku reanimacyjnym")],
    "mi": [("in a dead soldier's pouch", "w ładownicy martwego żołnierza"), ("in an ammo crate under a tarp", "w skrzyni z amunicją pod plandeką"),
           ("at the abandoned checkpoint", "na opuszczonym posterunku"), ("in a footlocker beneath a bunk", "w kufrze pod pryczą"),
           ("on a barricade the military left behind", "na barykadzie po wojsku")],
    "ca": [("on a shelf in the smokehouse", "na półce w wędzarni"), ("in a woven basket by the cistern", "w wiklinowym koszu przy cysternie"),
           ("in the hollow of a prayer-hall bench", "we wnęce ławy w domu modlitwy"), ("hung from a rafter in the weaving shed", "pod krokwią w tkalni"),
           ("in a sealed clay jar under the floor", "w zapieczętowanym glinianym dzbanie pod podłogą")],
    "ra": [("in the baggage cage", "w klatce bagażowej"), ("in a porter's locker", "w szafce bagażowego"), ("under the ticket counter", "pod okienkiem kasowym"),
           ("in the signal box's tool crate", "w skrzyni z narzędziami w nastawni"), ("in a coach left on the siding", "w wagonie na bocznicy")],
    "ma": [("in a tackle box on the pier", "w skrzynce wędkarskiej na pomoście"), ("in the harbourmaster's shed", "w szopie bosmana"),
           ("in the cabin of a beached boat", "w kajucie wyrzuconej na brzeg łodzi"), ("in a locker aboard a rusted trawler", "w szafce na zardzewiałym trawlerze"),
           ("in a dock crate half sunk in the silt", "w skrzyni portowej na wpół zatopionej w mule")],
    "hs": [("in a child's backpack under the bed", "w dziecięcym plecaku pod łóżkiem"), ("in the kitchen pantry", "w kuchennej spiżarni"),
           ("behind the false back of a wardrobe", "za podwójnym tyłem szafy"), ("in a shoebox in the attic", "w pudełku po butach na strychu"),
           ("in the cellar behind the jam shelves", "w piwnicy za półkami z przetworami")],
    "sc": [("in a teacher's desk drawer", "w szufladzie biurka nauczyciela"), ("in a child's backpack under the bleachers", "w dziecięcym plecaku pod trybunami"),
           ("in a cafeteria storeroom", "w magazynku stołówki"), ("in a locker with a broken lock", "w szafce ze zepsutym zamkiem"),
           ("in the nurse's office cupboard", "w szafce w gabinecie pielęgniarki")],
    "sh": [("under the shop counter", "pod ladą sklepu"), ("in the stock room behind a toppled shelf", "na zapleczu za przewróconym regałem"),
           ("in a display case with a broken pane", "w gablocie z wybitą szybą"), ("in a till drawer nobody emptied", "w szufladzie kasy, której nikt nie opróżnił"),
           ("in a delivery box nobody opened", "w paczce od dostawcy, której nikt nie otworzył")],
    "hw": [("in a bin at the back of the aisle", "w pojemniku na końcu alejki"), ("in the key-cutting counter drawer", "w szufladzie przy stanowisku do kopiowania kluczy"),
           ("under a pallet on the loading bay", "pod paletą na rampie"), ("in a locked tool cage", "w zamkniętej klatce z narzędziami"),
           ("in a toolbox on the workshop bench", "w skrzynce na warsztatowym stole")],
    "ht": [("in a hotel room nightstand", "w nocnej szafce w pokoju hotelowym"), ("behind the reception desk", "za recepcją"),
           ("in the minibar of a locked room", "w minibarku zamkniętego pokoju"), ("in a guest's suitcase", "w walizce gościa"),
           ("in the kitchen of the empty restaurant", "w kuchni pustej restauracji")],
    "wi": [("under a fallen log", "pod zwalonym pniem"), ("in a hunter's stash in a hollow tree", "w skrytce myśliwego w dziupli"),
           ("beside a long-dead campfire", "obok dawno wygasłego ogniska"), ("in a trapper's cabin", "w chacie traperskiej"),
           ("in a rusted ammo tin by the trail", "w zardzewiałej puszce po amunicji przy ścieżce")],
    "of": [("in a desk drawer on the second floor", "w szufladzie biurka na piętrze"), ("in a locked filing cabinet", "w zamkniętej kartotece"),
           ("in the manager's office safe", "w sejfie w gabinecie kierownika"), ("in the break-room cupboard", "w szafce w pokoju socjalnym"),
           ("in a briefcase under a desk", "w teczce pod biurkiem")],
    "fa": [("in the hen house", "w kurniku"), ("behind the barn door", "za drzwiami stodoły"), ("in the root cellar", "w piwnicy na warzywa"),
           ("on a vegetable patch gone wild", "na zdziczałej grządce"), ("in a feed sack in the shed", "w worku z paszą w szopie")],
}

# conditions: (EN, PL prefix, PL adjective (masculine nominative, ends in -y), quality -1 bad / 0 neutral / +1 good, categories ('*' = all))
CONDS = [
    ("rusted", "", "zardzewiały", -1, ("tool", "mat", "ammo", "part", "fuel")),
    ("dented", "", "wgnieciony", -1, ("food", "water", "tool", "fuel", "mat")),
    ("dusty", "", "zakurzony", -1, "*"),
    ("water-damaged", "", "zawilgocony", -1, ("book", "cloth", "trink", "seed")),
    ("mouldy", "", "spleśniały", -1, ("food", "cloth", "book")),
    ("stale", "", "czerstwy", -1, ("food",)),
    ("expired", "", "przeterminowany", -1, ("food", "med")),
    ("chipped", "", "wyszczerbiony", -1, ("tool", "trink", "mat")),
    ("scorched", "", "osmalony", -1, ("book", "cloth", "trink", "tool")),
    ("bloodstained", "", "zakrwawiony", -1, ("cloth", "med", "tool", "trink", "book", "part")),
    ("worn", "", "znoszony", -1, ("cloth",)),
    ("cracked", "", "pęknięty", -1, ("tool", "trink")),
    ("half-used", "do połowy ", "zużyty", 0, ("mat", "med", "tool", "fuel")),
    ("half-full", "do połowy ", "pełny", 0, ("water", "fuel")),
    ("faded", "", "wyblakły", 0, ("cloth", "book", "trink")),
    ("sealed", "", "nieotwarty", 1, ("food", "water", "med", "ammo", "seed")),
    ("factory-sealed", "", "zafoliowany", 1, ("food", "water", "med", "ammo", "part")),
    ("untouched", "", "nietknięty", 1, "*"),
    ("brand-new", "", "nowiutki", 1, ("tool", "cloth", "trink", "part", "mat", "book")),
    ("well-oiled", "", "naoliwiony", 1, ("tool", "part", "mat")),
    ("fully stocked", "w pełni ", "wyposażony", 1, ("med",)),
    ("still in its wrapping", "", "zapakowany", 1, ("cloth", "trink", "book", "tool")),
]

# story hooks: (EN, PL, flag).  {name} a first name written on it, {combo} a safe combination (flag 'lead': the next raid finds that safe), {note} a short note
NAMES = ["Danny", "Mia", "Rosa", "Eli", "June", "Owen", "Lena", "Ben", "Hana", "Cole"]
NOTES = [("Back by dark, don't wait up", "Wracam przed zmrokiem, nie czekaj"), ("For the baby, if she makes it", "Dla dziecka, jeśli przeżyje"),
         ("Do not open till spring", "Nie otwierać do wiosny"), ("We went north, follow the river", "Poszliśmy na północ, idźcie wzdłuż rzeki"),
         ("Whoever finds this, take it and keep going", "Kto to znajdzie, niech weźmie i idzie dalej")]
HOOKS = [
    ("A name is scratched on it: {name}.", "Ktoś wydrapał na tym imię: {name}.", ""),
    ("A folded note was tucked in with it: \"{note}.\"", "Razem z tym leżał złożony liścik: „{note}”.", ""),
    ("It had to be pried loose from a lock first.", "Najpierw trzeba było podważyć zamek.", ""),
    ("There was dried blood on it, and nobody asked whose.", "Było na tym trochę zaschniętej krwi i nikt nie pytał czyjej.", ""),
    ("It will buy a favour from the next trader through.", "Za to da się załatwić przysługę u następnego handlarza.", ""),
    ("A child's drawing was folded around it.", "Owinięto to dziecięcym rysunkiem.", ""),
    ("The dust says it had been waiting for years.", "Kurz mówił, że czekało to tam latami.", ""),
    ("It was hidden, not lost: somebody meant to come back.", "To było schowane, nie zgubione: ktoś zamierzał wrócić.", ""),
    ("The trap guarding it was still set.", "Pułapka, która tego pilnowała, była nadal napięta.", ""),
    ("A safe combination was scratched beside it: {combo}.", "Obok wydrapano kombinację do sejfu: {combo}.", "lead"),
    ("It was wrapped in a shirt that still smelled of someone's soap.", "Zawinięto to w koszulę, która wciąż pachniała czyimś mydłem.", ""),
    ("Two other crews had been through here; this was what they missed.", "Dwie inne ekipy już tu były; to jest to, co przeoczyły.", ""),
]

# the finding sentence, 4 forms.  EN: {who} {item} {loc} {Loc};  PL: {who} {item} {loc} {Loc} {a} (verb ending for a woman) {natknal} (natknął / natknęła)
SENT_EN = ["{who} found {item} {loc}.", "{Loc}, {who} came across {item}.", "{who} turned up {item} {loc}.", "{Loc} {who} spotted {item}."]
SENT_PL = ["{who} znalazł{a} {item} {loc}.", "{Loc}, {who} {natknal} się na {item}.", "{who} wygrzebał{a} {item} {loc}.", "{Loc} {who} wypatrzył{a} {item}."]
# the scraps / luxury flavour tail (EN, PL), by tier, sometimes appended
FLAVOR = {
    0: [("It is not much, but it is something.", "To niewiele, ale zawsze coś."), ("Barely worth the carrying.", "Ledwo warto to nieść.")],
    1: [("It will do.", "Wystarczy.")],
    3: [("A good day for it.", "Dobry dzień na taką rzecz.")],
    4: [("Nobody has seen the like in months.", "Od miesięcy nikt nie widział czegoś takiego."), ("It goes in the sack wrapped in the cleanest cloth they had.", "Do worka trafia owinięte w najczystszą szmatę, jaką mieli.")],
}
# keepsake callback (saga): what the clan did with a trinket / book, (EN, PL) with {k} the item in the nominative / {k_pl}

# ------------------------------------------------------------------ forms: what a thing is made of / how it is kept (hooks and conditions only fit some forms)
# forms: metal can jar bottle glass wood plastic paper cloth pack bag fresh animal liquid loose solid
CAT_FORM = {"food": "pack", "water": "bottle", "med": "pack", "ammo": "loose", "mat": "solid", "tool": "metal", "cloth": "cloth", "fuel": "can", "trink": "solid", "book": "paper",
            "seed": "pack", "anim": "animal", "part": "metal"}
FORM_ITEMS = {
    "can": "pine beans peaches sardines tuna tomsoup corn nolabel dogfood oats ham cocoa lampoil gunpowder coffee petrol",
    "jar": "honey jam pickles peanut salve nutsbolts buttons heirloom well marbles",
    "bottle": "oil whiskey wine waterbottle cloudy mineral sparkling soda tablets eyedrops syrup alcohol antiseptic supplements painkillers solvent gunoil perfume waterpack juice",
    "bag": "rice flour salt sugar jerky charcoal seedpotato mixedseed beanseed",
    "fresh": "fruit apples eggs berries mushrooms venison trout smokedfish crust",
    "liquid": "rainwater snowpot boiled canteen cistern waterskin",
    "wood": "planks firewood guitar chess musicbox rod arrows candles",
    "paper": "photo card newspaper",
    "cloth": "teddy doll patch rags cloth blanket sleepingbag backpack bandage dressing binding gauze tarp net boots scarf",
    "plastic": "cassette vinyl toycar radio gasmask sunglasses lighter tape flashlight lipstick",
    "glass": "thermometer",
    "loose": "r38 r22 shells bolts flares",
    "metal": "coin pendant ring watch dogtag harmonica propane diesel padlock lantern",
    "pack": "crackers noodles pasta cereal granola cookies tea chocolate matches abx abxbox box9 rifleammo aspirin firstaid trauma tomatoseed carrotseed hardtack",
}
FORM_OF = {k: f for f, ks in FORM_ITEMS.items() for k in ks.split()}

# conditions: the forms each may be given to (on top of the categories in CONDS)
COND_FORMS = {
    "rusted": ("metal", "can"), "dented": ("can", "metal"), "dusty": ("metal", "can", "jar", "bottle", "glass", "wood", "plastic", "paper", "cloth", "pack", "bag", "solid", "loose"),
    "water-damaged": ("paper", "cloth", "pack", "bag"), "mouldy": ("fresh", "pack", "bag", "paper", "cloth"), "stale": ("pack", "bag"), "expired": ("pack", "can", "jar", "bottle"),
    "chipped": ("solid", "glass", "wood", "plastic"), "scorched": ("paper", "cloth", "wood", "plastic", "solid"),
    "bloodstained": ("paper", "cloth", "bag", "pack", "wood", "plastic", "solid", "metal"), "worn": ("cloth",), "cracked": ("glass", "plastic", "wood"),
    "half-used": ("solid", "pack", "can", "jar"), "half-full": ("bottle", "can", "jar"), "faded": ("cloth", "paper", "plastic", "pack"),
    "sealed": ("can", "jar", "bottle", "pack", "bag"), "factory-sealed": ("pack", "bottle", "can", "jar"), "untouched": ("metal", "can", "jar", "bottle", "glass", "wood", "plastic", "paper", "cloth", "pack", "bag", "solid", "loose"),
    "brand-new": ("solid", "metal", "cloth", "plastic", "glass", "wood", "paper"), "well-oiled": ("metal",), "fully stocked": ("pack",),
    "still in its wrapping": ("cloth", "solid", "plastic", "paper", "wood", "metal"),
}

# items that take no condition at all (fresh food, living things, liquids that are what they are) and conditions an item cannot have
NO_COND = frozenset("fruit apples eggs berries mushrooms venison trout smokedfish rainwater snowpot boiled hens goat rabbits beehive firewood ducks piglet".split())
COND_BAN = {"r38": {"sealed", "factory-sealed", "untouched"}, "r22": {"sealed", "factory-sealed", "untouched"}, "shells": {"sealed", "factory-sealed", "untouched"},
            "arrows": {"sealed", "factory-sealed", "untouched"}, "bolts": {"sealed", "factory-sealed", "untouched"}, "flares": {"sealed", "factory-sealed"},
            "canteen": {"expired", "dented", "sealed", "factory-sealed"}, "scrap": {"brand-new", "well-oiled", "untouched"}, "rags": {"brand-new", "well-oiled", "untouched"},
            "crust": {"sealed", "factory-sealed", "untouched", "dented"}, "nolabel": {"sealed", "factory-sealed", "mouldy", "stale"}, "dogfood": {"mouldy", "stale"},
            "bandage": {"expired", "dented"}, "tablets": {"half-full"}, "waterbottle": {"expired", "mouldy"}}

# hooks: which forms each accepts (index = HOOKS index; None = any).  A name SCRATCHED needs a hard surface, a name WRITTEN needs a label, a note needs a container, ...
_SOLID = ("metal", "can", "jar", "bottle", "glass", "wood", "plastic", "paper", "cloth", "pack", "bag", "solid")
HOOK_FORMS = [
    ("metal", "can", "wood", "plastic", "solid"),                     # 0 name scratched on it
    ("bag", "pack", "paper", "cloth"),                                # 1 folded note tucked in with it
    ("metal", "wood", "plastic", "solid", "pack"),                    # 2 pried loose from a lock
    _SOLID,                                                           # 3 dried blood on it
    None,                                                             # 4 a favour from the next trader
    ("metal", "can", "jar", "bottle", "wood", "plastic", "solid", "pack"),   # 5 a child's drawing folded around it
    _SOLID,                                                           # 6 the dust says it waited for years
    None,                                                             # 7 hidden, not lost
    None,                                                             # 8 the trap guarding it
    None,                                                             # 9 a safe combination beside it
    ("metal", "can", "jar", "bottle", "glass", "wood", "plastic", "paper", "pack", "solid"),   # 10 wrapped in a shirt
    None,                                                             # 11 two other crews
    ("can", "jar", "bottle", "pack"),                                 # 12 name written on the label
    ("cloth",),                                                       # 13 name stitched inside
    ("paper",),                                                       # 14 name written inside the cover
]
HOOKS += [
    ("A name is written on the label in marker: {name}.", "Na etykiecie ktoś napisał markerem imię: {name}.", ""),
    ("A name is stitched inside: {name}.", "W środku wyszyto imię: {name}.", ""),
    ("A name is written inside the cover: {name}.", "Na wewnętrznej stronie okładki napisano imię: {name}.", ""),
]
