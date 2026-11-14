"""Polish data of the clan saga (tools/clan_saga_pl.py): every English word group the saga puts into a template, in the Polish forms the Polish templates use.

Names of people are never declined (the Polish templates keep them in the nominative and use pronoun forms {A?go|ją} for the other cases, like tools/clan_story_pl.py).
Noun groups come with the cases the templates need.  Keyed by the English string the saga produces (tools/clan_saga_data.py, tools/clan_saga.py).
"""

# ---------------------------------------------------------------- places: EN -> (nom, gen, prep, loc, ins)   at = prep + loc, to = "do " + gen, from = "z " + gen
PLACES = {
    # Forest
    "the fallen fir over the creek": ("zwalona jodła nad potokiem", "zwalonej jodły nad potokiem", "przy", "zwalonej jodle nad potokiem", "zwaloną jodłą nad potokiem"),
    "the hunting blind": ("ambona myśliwska", "ambony myśliwskiej", "na", "ambonie myśliwskiej", "amboną myśliwską"),
    "the deer trail": ("ścieżka jeleni", "ścieżki jeleni", "na", "ścieżce jeleni", "ścieżką jeleni"),
    "the mossy culvert": ("porośnięty mchem przepust", "porośniętego mchem przepustu", "w", "porośniętym mchem przepuście", "porośniętym mchem przepustem"),
    "the burned cabin": ("spalona chata", "spalonej chaty", "przy", "spalonej chacie", "spaloną chatą"),
    # Gas Station
    "the pump island": ("wysepka z dystrybutorami", "wysepki z dystrybutorami", "przy", "wysepce z dystrybutorami", "wysepką z dystrybutorami"),
    "the cooler aisle": ("alejka z lodówkami", "alejki z lodówkami", "w", "alejce z lodówkami", "alejką z lodówkami"),
    "the garage bay": ("stanowisko w garażu", "stanowiska w garażu", "na", "stanowisku w garażu", "stanowiskiem w garażu"),
    "the dumpster yard": ("podwórko ze śmietnikami", "podwórka ze śmietnikami", "na", "podwórku ze śmietnikami", "podwórkiem ze śmietnikami"),
    "the roof sign": ("szyld na dachu", "szyldu na dachu", "pod", "szyldem na dachu", "szyldem na dachu"),
    # School
    "the gym": ("sala gimnastyczna", "sali gimnastycznej", "w", "sali gimnastycznej", "salą gimnastyczną"),
    "the east stairwell": ("wschodnia klatka schodowa", "wschodniej klatki schodowej", "na", "wschodniej klatce schodowej", "wschodnią klatką schodową"),
    "the cafeteria": ("stołówka", "stołówki", "w", "stołówce", "stołówką"),
    "the principal's office": ("gabinet dyrektora", "gabinetu dyrektora", "w", "gabinecie dyrektora", "gabinetem dyrektora"),
    "the bus loop": ("pętla autobusowa", "pętli autobusowej", "na", "pętli autobusowej", "pętlą autobusową"),
    # Shipyard
    "the crane cab": ("kabina dźwigu", "kabiny dźwigu", "w", "kabinie dźwigu", "kabiną dźwigu"),
    "the container maze": ("labirynt kontenerów", "labiryntu kontenerów", "w", "labiryncie kontenerów", "labiryntem kontenerów"),
    "the dry dock": ("suchy dok", "suchego doku", "w", "suchym doku", "suchym dokiem"),
    "the welding shed": ("spawalnia", "spawalni", "w", "spawalni", "spawalnią"),
    "the east pier": ("wschodnie molo", "wschodniego mola", "na", "wschodnim molo", "wschodnim molo"),
    # Resort
    "the pool deck": ("taras przy basenie", "tarasu przy basenie", "na", "tarasie przy basenie", "tarasem przy basenie"),
    "the lobby bar": ("bar w holu", "baru w holu", "w", "barze w holu", "barem w holu"),
    "the boathouse": ("hangar na łodzie", "hangaru na łodzie", "w", "hangarze na łodzie", "hangarem na łodzie"),
    "the golf cart shed": ("szopa na wózki golfowe", "szopy na wózki golfowe", "w", "szopie na wózki golfowe", "szopą na wózki golfowe"),
    "the east chalets": ("wschodnie domki", "wschodnich domków", "w", "wschodnich domkach", "wschodnimi domkami"),
    # Seraphite Camp
    "the cistern": ("cysterna", "cysterny", "przy", "cysternie", "cysterną"),
    "the prayer hall": ("sala modlitw", "sali modlitw", "w", "sali modlitw", "salą modlitw"),
    "the rope bridge": ("most linowy", "mostu linowego", "na", "moście linowym", "mostem linowym"),
    "the smokehouse": ("wędzarnia", "wędzarni", "w", "wędzarni", "wędzarnią"),
    "the weaving shed": ("tkalnia", "tkalni", "w", "tkalni", "tkalnią"),
    # Houses
    "the corner house": ("dom na rogu", "domu na rogu", "w", "domu na rogu", "domem na rogu"),
    "the garage": ("garaż", "garażu", "w", "garażu", "garażem"),
    "the back fence": ("tylne ogrodzenie", "tylnego ogrodzenia", "przy", "tylnym ogrodzeniu", "tylnym ogrodzeniem"),
    "the porch with the swing": ("ganek z huśtawką", "ganku z huśtawką", "na", "ganku z huśtawką", "gankiem z huśtawką"),
    "the cellar stairs": ("schody do piwnicy", "schodów do piwnicy", "na", "schodach do piwnicy", "schodami do piwnicy"),
    # Hospital
    "the east ward": ("wschodni oddział", "wschodniego oddziału", "na", "wschodnim oddziale", "wschodnim oddziałem"),
    "the pharmacy cage": ("zakratowana apteka", "zakratowanej apteki", "w", "zakratowanej aptece", "zakratowaną apteką"),
    "the lobby atrium": ("atrium w holu", "atrium w holu", "w", "atrium w holu", "atrium w holu"),
    "the morgue corridor": ("korytarz do kostnicy", "korytarza do kostnicy", "na", "korytarzu do kostnicy", "korytarzem do kostnicy"),
    "the ambulance bay": ("podjazd dla karetek", "podjazdu dla karetek", "na", "podjeździe dla karetek", "podjazdem dla karetek"),
    # Hardware Store
    "the paint aisle": ("dział z farbami", "działu z farbami", "w", "dziale z farbami", "działem z farbami"),
    "the nail bins": ("pojemniki z gwoździami", "pojemników z gwoździami", "przy", "pojemnikach z gwoździami", "pojemnikami z gwoździami"),
    "the loading dock": ("rampa załadunkowa", "rampy załadunkowej", "na", "rampie załadunkowej", "rampą załadunkową"),
    "the lumber yard": ("skład drewna", "składu drewna", "na", "składzie drewna", "składem drewna"),
    "the key-cutting counter": ("stoisko z kluczami", "stoiska z kluczami", "przy", "stoisku z kluczami", "stoiskiem z kluczami"),
    # Motel
    "room nine": ("pokój numer dziewięć", "pokoju numer dziewięć", "w", "pokoju numer dziewięć", "pokojem numer dziewięć"),
    "the ice machine": ("automat z lodem", "automatu z lodem", "przy", "automacie z lodem", "automatem z lodem"),
    "the front office": ("recepcja", "recepcji", "w", "recepcji", "recepcją"),
    "the dry pool": ("pusty basen", "pustego basenu", "przy", "pustym basenie", "pustym basenem"),
    "the parking lot": ("parking", "parkingu", "na", "parkingu", "parkingiem"),
    # Hillcrest
    "the water tower": ("wieża ciśnień", "wieży ciśnień", "pod", "wieżą ciśnień", "wieżą ciśnień"),
    "the church steps": ("schody kościoła", "schodów kościoła", "na", "schodach kościoła", "schodami kościoła"),
    "the bakery": ("piekarnia", "piekarni", "w", "piekarni", "piekarnią"),
    "the cul-de-sac": ("ślepa uliczka", "ślepej uliczki", "w", "ślepej uliczce", "ślepą uliczką"),
    "the clinic basement": ("piwnica przychodni", "piwnicy przychodni", "w", "piwnicy przychodni", "piwnicą przychodni"),
    # TV Station
    "the studio floor": ("hala studia", "hali studia", "w", "hali studia", "halą studia"),
    "the control room": ("reżyserka", "reżyserki", "w", "reżyserce", "reżyserką"),
    "the antenna stairs": ("schody na maszt", "schodów na maszt", "na", "schodach na maszt", "schodami na maszt"),
    "the green room": ("garderoba", "garderoby", "w", "garderobie", "garderobą"),
    "the car park": ("parking", "parkingu", "na", "parkingu", "parkingiem"),
    # Train Station
    "the ticket hall": ("hala biletowa", "hali biletowej", "w", "hali biletowej", "halą biletową"),
    "the platform": ("peron", "peronu", "na", "peronie", "peronem"),
    "the baggage cage": ("przechowalnia bagażu", "przechowalni bagażu", "w", "przechowalni bagażu", "przechowalnią bagażu"),
    "the signal box": ("nastawnia", "nastawni", "w", "nastawni", "nastawnią"),
    "the footbridge": ("kładka", "kładki", "na", "kładce", "kładką"),
    # Downtown
    "the bank lobby": ("hol banku", "holu banku", "w", "holu banku", "holem banku"),
    "the bus lanes": ("buspasy", "buspasów", "na", "buspasach", "buspasami"),
    "the fountain square": ("plac z fontanną", "placu z fontanną", "na", "placu z fontanną", "placem z fontanną"),
    "the parking garage": ("garaż wielopoziomowy", "garażu wielopoziomowego", "w", "garażu wielopoziomowym", "garażem wielopoziomowym"),
    "the tram wire alley": ("zaułek pod trakcją tramwajową", "zaułka pod trakcją tramwajową", "w", "zaułku pod trakcją tramwajową", "zaułkiem pod trakcją tramwajową"),
    # Lodge
    "the great hall": ("wielka sala", "wielkiej sali", "w", "wielkiej sali", "wielką salą"),
    "the antler stairs": ("schody z porożami", "schodów z porożami", "na", "schodach z porożami", "schodami z porożami"),
    "the boat shed": ("szopa na łodzie", "szopy na łodzie", "w", "szopie na łodzie", "szopą na łodzie"),
    "the trophy room": ("sala trofeów", "sali trofeów", "w", "sali trofeów", "salą trofeów"),
    "the long porch": ("długa weranda", "długiej werandy", "na", "długiej werandzie", "długą werandą"),
    # Jackson Suburbs
    "the playground": ("plac zabaw", "placu zabaw", "na", "placu zabaw", "placem zabaw"),
    "the snowed-in garage": ("zasypany śniegiem garaż", "zasypanego śniegiem garażu", "w", "zasypanym śniegiem garażu", "zasypanym śniegiem garażem"),
    "the gate wall": ("mur przy bramie", "muru przy bramie", "na", "murze przy bramie", "murem przy bramie"),
    "the stranded school bus": ("porzucony autobus szkolny", "porzuconego autobusu szkolnego", "w", "porzuconym autobusie szkolnym", "porzuconym autobusem szkolnym"),
    # Suburbs
    "the three-car garage": ("garaż na trzy auta", "garażu na trzy auta", "w", "garażu na trzy auta", "garażem na trzy auta"),
    "the back porch": ("tylny ganek", "tylnego ganku", "na", "tylnym ganku", "tylnym gankiem"),
    "the kitchen with the bay window": ("kuchnia z oknem wykuszowym", "kuchni z oknem wykuszowym", "w", "kuchni z oknem wykuszowym", "kuchnią z oknem wykuszowym"),
    "the mailbox row": ("rząd skrzynek na listy", "rzędu skrzynek na listy", "przy", "rzędzie skrzynek na listy", "rzędem skrzynek na listy"),
    # Bookstore
    "the poetry shelves": ("regały z poezją", "regałów z poezją", "przy", "regałach z poezją", "regałami z poezją"),
    "the cafe counter": ("lada kawiarni", "lady kawiarni", "przy", "ladzie kawiarni", "ladą kawiarni"),
    "the stock room": ("magazyn", "magazynu", "w", "magazynie", "magazynem"),
    "the upstairs gallery": ("galeria na piętrze", "galerii na piętrze", "na", "galerii na piętrze", "galerią na piętrze"),
    "the display window": ("witryna", "witryny", "przy", "witrynie", "witryną"),
    # Hillside
    "the gate": ("brama", "bramy", "przy", "bramie", "bramą"),
    "the switchback road": ("serpentyna", "serpentyny", "na", "serpentynie", "serpentyną"),
    "the chapel": ("kaplica", "kaplicy", "w", "kaplicy", "kaplicą"),
    "the retaining wall": ("mur oporowy", "muru oporowego", "przy", "murze oporowym", "murem oporowym"),
    "the lookout": ("punkt widokowy", "punktu widokowego", "na", "punkcie widokowym", "punktem widokowym"),
    # Capitol Hill Shops
    "the record store": ("sklep płytowy", "sklepu płytowego", "w", "sklepie płytowym", "sklepem płytowym"),
    "the laundromat": ("pralnia samoobsługowa", "pralni samoobsługowej", "w", "pralni samoobsługowej", "pralnią samoobsługową"),
    "the awning row": ("rząd markiz", "rzędu markiz", "pod", "markizami", "rzędem markiz"),
    "the back alley": ("tylna uliczka", "tylnej uliczki", "w", "tylnej uliczce", "tylną uliczką"),
    # Convention Center
    "the escalators": ("schody ruchome", "schodów ruchomych", "na", "schodach ruchomych", "schodami ruchomymi"),
    "the exhibition hall": ("hala wystawowa", "hali wystawowej", "w", "hali wystawowej", "halą wystawową"),
    "the loading ramp": ("rampa załadunkowa", "rampy załadunkowej", "na", "rampie załadunkowej", "rampą załadunkową"),
    "the registration desks": ("stanowiska rejestracji", "stanowisk rejestracji", "przy", "stanowiskach rejestracji", "stanowiskami rejestracji"),
    "the catwalk": ("kładka techniczna", "kładki technicznej", "na", "kładce technicznej", "kładką techniczną"),
    # Overpass
    "the collapsed span": ("zawalone przęsło", "zawalonego przęsła", "na", "zawalonym przęśle", "zawalonym przęsłem"),
    "the bus on its side": ("autobus na boku", "autobusu na boku", "przy", "autobusie na boku", "autobusem na boku"),
    "the guardrail": ("bariera ochronna", "bariery ochronnej", "przy", "barierze ochronnej", "barierą ochronną"),
    "the underpass": ("przejście podziemne", "przejścia podziemnego", "w", "przejściu podziemnym", "przejściem podziemnym"),
    "the toll booth": ("budka poborcy opłat", "budki poborcy opłat", "w", "budce poborcy opłat", "budką poborcy opłat"),
    # generic map
    "the main hall": ("główna hala", "głównej hali", "w", "głównej hali", "główną halą"),
    "the back stairs": ("tylne schody", "tylnych schodów", "na", "tylnych schodach", "tylnymi schodami"),
    "the yard": ("podwórze", "podwórza", "na", "podwórzu", "podwórzem"),
    "the loading door": ("drzwi załadunkowe", "drzwi załadunkowych", "przy", "drzwiach załadunkowych", "drzwiami załadunkowymi"),
    "the roof": ("dach", "dachu", "na", "dachu", "dachem"),
    # fallbacks the saga uses when there is no map
    "the east wall": ("wschodni mur", "wschodniego muru", "przy", "wschodnim murze", "wschodnim murem"),
    "the next map": ("następna mapa", "następnej mapy", "na", "następnej mapie", "następną mapą"),
    "a raid": ("wypad", "wypadu", "na", "wypadzie", "wypadem"),
    "raid": ("wypad", "wypadu", "na", "wypadzie", "wypadem"),
}

# ---------------------------------------------------------------- maps: the game's own Polish names (tools/clan_chronicle_maps.py PL) -> (nom, gen, prep, loc, ins)  (lower case in running text)
MAPS = {
    "Forest": ("las", "lasu", "w", "lesie", "lasem"),
    "Gas Station": ("stacja benzynowa", "stacji benzynowej", "na", "stacji benzynowej", "stacją benzynową"),
    "School": ("szkoła", "szkoły", "w", "szkole", "szkołą"),
    "Shipyard": ("stocznia", "stoczni", "w", "stoczni", "stocznią"),
    "Resort": ("ośrodek", "ośrodka", "w", "ośrodku", "ośrodkiem"),
    "Seraphite Camp": ("obóz Serafitów", "obozu Serafitów", "w", "obozie Serafitów", "obozem Serafitów"),
    "Houses": ("domy", "domów", "w", "domach", "domami"),
    "Hospital": ("szpital", "szpitala", "w", "szpitalu", "szpitalem"),
    "Hardware Store": ("sklep z narzędziami", "sklepu z narzędziami", "w", "sklepie z narzędziami", "sklepem z narzędziami"),
    "Motel": ("motel", "motelu", "w", "motelu", "motelem"),
    "Hillcrest": ("Hillcrest", "Hillcrest", "w", "Hillcrest", "Hillcrest"),
    "TV Station": ("stacja telewizyjna", "stacji telewizyjnej", "w", "stacji telewizyjnej", "stacją telewizyjną"),
    "Train Station": ("dworzec kolejowy", "dworca kolejowego", "na", "dworcu kolejowym", "dworcem kolejowym"),
    "Downtown": ("śródmieście", "śródmieścia", "w", "śródmieściu", "śródmieściem"),
    "Lodge": ("leśniczówka", "leśniczówki", "w", "leśniczówce", "leśniczówką"),
    "Jackson Suburbs": ("przedmieścia Jackson", "przedmieść Jackson", "na", "przedmieściach Jackson", "przedmieściami Jackson"),
    "Suburbs": ("przedmieścia", "przedmieść", "na", "przedmieściach", "przedmieściami"),
    "Bookstore": ("księgarnia", "księgarni", "w", "księgarni", "księgarnią"),
    "Hillside": ("zbocze", "zbocza", "na", "zboczu", "zboczem"),
    "Capitol Hill Shops": ("sklepy na Capitol Hill", "sklepów na Capitol Hill", "w", "sklepach na Capitol Hill", "sklepami na Capitol Hill"),
    "Convention Center": ("centrum konferencyjne", "centrum konferencyjnego", "w", "centrum konferencyjnym", "centrum konferencyjnym"),
    "Overpass": ("wiadukt", "wiaduktu", "na", "wiadukcie", "wiaduktem"),
}

# ---------------------------------------------------------------- the smell / sound of ...: EN phrase after "the smell of " / "the sound of " -> Polish genitive after zapach / dźwięk
AIR = {
    "wet moss and fir sap": "wilgotnego mchu i żywicy jodłowej", "a creek running under ice": "potoku płynącego pod lodem", "old woodsmoke": "starego dymu z ogniska",
    "old petrol and rat droppings": "starej benzyny i szczurzych odchodów", "a loose sign knocking in the wind": "obluzowanego szyldu stukającego na wietrze",
    "burnt rubber": "palonej gumy",
    "floor wax and mildew": "pasty do podłóg i pleśni", "a locker door swinging on one hinge": "drzwiczek szafki chwiejących się na jednym zawiasie",
    "chalk dust and damp paper": "kredowego pyłu i wilgotnego papieru",
    "rust and tar": "rdzy i smoły", "chains ringing against a hull": "łańcuchów dzwoniących o kadłub", "diesel and cold salt": "oleju napędowego i zimnej soli",
    "chlorine long gone green": "chloru, który dawno zzielenił wodę", "a banner flapping above the lobby": "transparentu łopoczącego nad holem", "mildewed carpet": "spleśniałej wykładziny",
    "smoked fish and lamp oil": "wędzonej ryby i oliwy do lamp", "wind through the rope bridge": "wiatru w linowym moście", "wet cloth and ash": "mokrego płótna i popiołu",
    "damp curtains and cat": "wilgotnych zasłon i kota", "a screen door slapping": "trzaskających drzwi z siatką", "cold ash in a fireplace": "zimnego popiołu w kominku",
    "old disinfectant and something sweeter underneath": "starego środka dezynfekującego i czegoś słodszego pod spodem",
    "a gurney wheel squealing somewhere": "piszczącego gdzieś kółka noszy", "mould in the ceiling tiles": "pleśni w płytach sufitu",
    "cut pine and machine oil": "ciętej sosny i oleju maszynowego", "loose screws rolling over concrete": "luźnych śrub toczących się po betonie", "dried paint": "zaschniętej farby",
    "stale cigarettes and cheap carpet": "zwietrzałych papierosów i taniej wykładziny", "a vending machine humming to nobody": "automatu z przekąskami, który szumi do nikogo",
    "bleach on old stains": "wybielacza na starych plamach",
    "cold stone and rain": "zimnego kamienia i deszczu", "a church bell with no rope": "kościelnego dzwonu bez liny", "burnt flour": "przypalonej mąki",
    "hot dust and old cables": "gorącego kurzu i starych kabli", "static from a monitor that still has power": "szumu z monitora, który wciąż ma prąd", "stale coffee": "zwietrzałej kawy",
    "rust and pigeon dung": "rdzy i gołębich odchodów", "water dripping on the rails": "wody kapiącej na szyny", "cold iron": "zimnego żelaza",
    "brick dust and wet glass": "ceglanego pyłu i mokrego szkła", "traffic lights ticking over for no one": "sygnalizacji przełączającej się dla nikogo", "old fires": "dawnych pożarów",
    "cold hearth and elk hide": "zimnego paleniska i skóry łosia", "a shutter creaking in the lake wind": "okiennicy skrzypiącej na jeziornym wietrze", "pine resin": "żywicy sosnowej",
    "snow melting on warm stone": "śniegu topniejącego na ciepłym kamieniu", "a swing chain creaking": "skrzypiącego łańcucha huśtawki", "woodsmoke and horse": "dymu z drewna i konia",
    "mould in carpet and cat": "pleśni w dywanie i kota", "a distant dog that is not a dog": "odległego psa, który nie jest psem", "damp drywall": "wilgotnych płyt kartonowo-gipsowych",
    "mildewed paper and spilled coffee": "spleśniałego papieru i rozlanej kawy", "pages rustling in a draught": "szeleszczących stron w przeciągu", "dust and glue": "kurzu i kleju",
    "wet clay and rust": "mokrej gliny i rdzy", "gravel sliding down the slope": "żwiru osuwającego się po zboczu", "cold pine": "zimnej sosny",
    "stale bread and vinyl": "czerstwego chleba i winylu", "a loose awning drumming in the wind": "luźnej markizy bębniącej na wietrze", "old soap": "starego mydła",
    "dust and carpet glue": "kurzu i kleju do wykładziny", "footsteps carried a hundred yards by the concrete": "kroków niesionych przez beton na sto metrów", "mould": "pleśni",
    "wet concrete and exhaust long gone": "mokrego betonu i dawno wywietrzałych spalin", "wind whistling through rebar": "wiatru gwiżdżącego w prętach zbrojeniowych", "old tar": "starej smoły",
    "dust and mould": "kurzu i pleśni", "a loose sheet of tin banging": "obluzowanej blachy łomoczącej na wietrze", "cold ash": "zimnego popiołu",
}

CAMPS = {
    "the east barracks": ("wschodnie koszary", "wschodnich koszar", "w", "wschodnich koszarach", "wschodnimi koszarami"),
    "the FOB mess": ("stołówka bazy", "stołówki bazy", "w", "stołówce bazy", "stołówką bazy"),
    "the old gym": ("stara sala gimnastyczna", "starej sali gimnastycznej", "w", "starej sali gimnastycznej", "starą salą gimnastyczną"),
    "the pharmacy block": ("blok z apteką", "bloku z apteką", "w", "bloku z apteką", "blokiem z apteką"),
    "the stadium tunnel": ("tunel stadionu", "tunelu stadionu", "w", "tunelu stadionu", "tunelem stadionu"),
    "the long house": ("długi dom", "długiego domu", "w", "długim domu", "długim domem"),
    "the kitchen house": ("dom kuchenny", "domu kuchennego", "w", "domu kuchennym", "domem kuchennym"),
    "the weaving house": ("tkalnia", "tkalni", "w", "tkalni", "tkalnią"),
    "the shore camp": ("obóz na brzegu", "obozu na brzegu", "w", "obozie na brzegu", "obozem na brzegu"),
    "the harbor hut": ("chata w przystani", "chaty w przystani", "w", "chacie w przystani", "chatą w przystani"),
}

# leader: EN -> (nom, gen, ins)  (only used in W-scoped templates: "Dowództwo" is neuter)
LEADERS = {"Command": ("Dowództwo", "Dowództwa", "Dowództwem"), "the Prophet": ("Prorok", "Proroka", "Prorokiem")}
# the faction the player fights: ("Blizny"...) nom = acc, gen, ins, dat, loc, singular genitive (for "kula Blizny")
ENEMIES = {"the Scars": ("Blizny", "Blizn", "Bliznami", "Bliznom", "Bliznach", "Blizny"), "the Wolves": ("Wilki", "Wilków", "Wilkami", "Wilkom", "Wilkach", "Wilka")}

# body sites: EN -> (nom, gen, acc, loc, ins)    "na " + loc,  "w " + acc
SITES = {
    "left eyebrow": ("lewa brew", "lewej brwi", "lewą brew", "lewej brwi", "lewą brwią"),
    "right shoulder": ("prawe ramię", "prawego ramienia", "prawe ramię", "prawym ramieniu", "prawym ramieniem"),
    "left forearm": ("lewe przedramię", "lewego przedramienia", "lewe przedramię", "lewym przedramieniu", "lewym przedramieniem"),
    "ribs": ("żebra", "żeber", "żebra", "żebrach", "żebrami"),
    "right thigh": ("prawe udo", "prawego uda", "prawe udo", "prawym udzie", "prawym udem"),
    "scalp": ("skóra głowy", "skóry głowy", "skórę głowy", "skórze głowy", "skórą głowy"),
    "left hand": ("lewa dłoń", "lewej dłoni", "lewą dłoń", "lewej dłoni", "lewą dłonią"),
    "calf": ("łydka", "łydki", "łydkę", "łydce", "łydką"),
    "right ankle": ("prawa kostka", "prawej kostki", "prawą kostkę", "prawej kostce", "prawą kostką"),
    "jaw": ("szczęka", "szczęki", "szczękę", "szczęce", "szczęką"),
    "left shoulder": ("lewe ramię", "lewego ramienia", "lewe ramię", "lewym ramieniu", "lewym ramieniem"),
    "palm": ("dłoń", "dłoni", "dłoń", "dłoni", "dłonią"),
}
CLOTHS = {
    "a strip of bedsheet": ("pasek prześcieradła", "paska prześcieradła", "paskiem prześcieradła"),
    "boiled rag": ("wygotowana szmata", "wygotowanej szmaty", "wygotowaną szmatą"),
    "gauze that was washed twice": ("dwukrotnie prana gaza", "dwukrotnie pranej gazy", "dwukrotnie praną gazą"),
    "a torn shirt sleeve": ("urwany rękaw koszuli", "urwanego rękawa koszuli", "urwanym rękawem koszuli"),
    "waxed cord and a clean sock": ("woskowany sznurek i czysta skarpeta", "woskowanego sznurka i czystej skarpety", "woskowanym sznurkiem i czystą skarpetą"),
    "a bandage with a stain the colour of tea": ("bandaż z plamą w kolorze herbaty", "bandaża z plamą w kolorze herbaty", "bandażem z plamą w kolorze herbaty"),
}
# causes: index of SD.CAUSES -> (acc, gen, ins); {e} = the singular genitive of the opposing faction
CAUSES = [
    ("kulę {e}", "kuli {e}", "kulą {e}"),
    ("topór {e}", "topora {e}", "toporem {e}"),
    ("bełt z łuku {e}", "bełtu z łuku {e}", "bełtem z łuku {e}"),
    ("odłamek bomby gwoździowej", "odłamka bomby gwoździowej", "odłamkiem bomby gwoździowej"),
    ("ostrze rozbitej butelki", "ostrza rozbitej butelki", "ostrzem rozbitej butelki"),
    ("nóż {e}", "noża {e}", "nożem {e}"),
    ("rurę {e}", "rury {e}", "rurą {e}"),
    ("ładunek ze strzelby {e}", "ładunku ze strzelby {e}", "ładunkiem ze strzelby {e}"),
]
# jobs: EN -> (infinitive, negated infinitive)
JOBS = {
    "carry a full sack": ("nosić pełny worek", "nosić pełnego worka"), "hold the lamp steady": ("trzymać lampę nieruchomo", "trzymać lampy nieruchomo"),
    "lift the big pot": ("podnieść duży garnek", "podnieść dużego garnka"), "walk the wall": ("obchodzić mur", "obchodzić muru"),
    "work the vice": ("pracować przy imadle", "pracować przy imadle"), "climb the roof": ("wchodzić na dach", "wchodzić na dach"),
    "dig the beds": ("kopać grządki", "kopać grządek"), "chase the others": ("ganiać za resztą", "ganiać za resztą"),
    "take the stairs": ("chodzić po schodach", "chodzić po schodach"), "turn the crank": ("kręcić korbą", "kręcić korbą"), "work": ("pracować", "pracować"),
}
# fears: EN -> (genitive after "boi się", what the person does)
FEARS = {
    "the dark": ("ciemności", "przed każdym korytarzem kładzie dłoń na ścianie"),
    "water": ("wody", "nie przejdzie przez potok, jeśli ktoś nie trzyma liny"),
    "fire": ("ognia", "wzdryga się przy każdej zapalonej zapałce"),
    "dogs": ("psów", "obchodzi psi dziedziniec dookoła zamiast przez środek"),
    "tall grass": ("wysokiej trawy", "nigdy nie wchodzi w nią bez kija"),
    "closed doors": ("zamkniętych drzwi", "każde drzwi podpiera butem"),
    "clickers": ("klikaczy", "zamiera, gdy kran kapie dwa razy w tym samym rytmie"),
    "being alone": ("samotności", "śpi przy piecu, tam gdzie przechodzą inni"),
    "heights": ("wysokości", "idzie naokoło każdych schodów z dziurą"),
    "the quiet": ("ciszy", "nuci, kiedy w pokoju robi się cicho"),
}
# possessions: EN -> (nom, acc, gen, ins)
POSS = {
    "a dead watch": ("martwy zegarek", "martwy zegarek", "martwego zegarka", "martwym zegarkiem"),
    "a photograph with the face worn off": ("fotografia z wytartą twarzą", "fotografię z wytartą twarzą", "fotografii z wytartą twarzą", "fotografią z wytartą twarzą"),
    "a tin whistle": ("blaszany gwizdek", "blaszany gwizdek", "blaszanego gwizdka", "blaszanym gwizdkiem"),
    "a lucky bullet on a string": ("szczęśliwa kula na sznurku", "szczęśliwą kulę na sznurku", "szczęśliwej kuli na sznurku", "szczęśliwą kulą na sznurku"),
    "a pocket knife with a cracked handle": ("składany nóż z pękniętą rączką", "składany nóż z pękniętą rączką", "składanego noża z pękniętą rączką", "składanym nożem z pękniętą rączką"),
    "a child's shoe": ("dziecięcy bucik", "dziecięcy bucik", "dziecięcego buciku", "dziecięcym bucikiem"),
    "a scrap of blue ribbon": ("skrawek niebieskiej wstążki", "skrawek niebieskiej wstążki", "skrawka niebieskiej wstążki", "skrawkiem niebieskiej wstążki"),
    "a notebook with half the pages gone": ("notes z wyrwaną połową kartek", "notes z wyrwaną połową kartek", "notesu z wyrwaną połową kartek", "notesem z wyrwaną połową kartek"),
    "a dented lighter": ("wgnieciona zapalniczka", "wgniecioną zapalniczkę", "wgniecionej zapalniczki", "wgniecioną zapalniczką"),
    "a jar of buttons": ("słoik guzików", "słoik guzików", "słoika guzików", "słoikiem guzików"),
    "a folded map of a place long gone": ("złożona mapa miejsca, którego już nie ma", "złożoną mapę miejsca, którego już nie ma",
                                           "złożonej mapy miejsca, którego już nie ma", "złożoną mapą miejsca, którego już nie ma"),
    "a wedding ring on a shoelace": ("obrączka na sznurówce", "obrączkę na sznurówce", "obrączki na sznurówce", "obrączką na sznurówce"),
    "a ceramic cup with no handle": ("ceramiczny kubek bez ucha", "ceramiczny kubek bez ucha", "ceramicznego kubka bez ucha", "ceramicznym kubkiem bez ucha"),
    "a harmonica key": ("kluczyk do harmonijki", "kluczyk do harmonijki", "kluczyka do harmonijki", "kluczykiem do harmonijki"),
    "a pair of reading glasses held with tape": ("okulary do czytania sklejone taśmą", "okulary do czytania sklejone taśmą", "okularów do czytania sklejonych taśmą",
                                                   "okularami do czytania sklejonymi taśmą"),
    "a postcard of the sea": ("pocztówka z morzem", "pocztówkę z morzem", "pocztówki z morzem", "pocztówką z morzem"),
    "a plastic dinosaur": ("plastikowy dinozaur", "plastikowy dinozaur", "plastikowego dinozaura", "plastikowym dinozaurem"),
    "a pair of boots too big for anyone": ("para butów za dużych dla każdego", "parę butów za dużych dla każdego", "pary butów za dużych dla każdego",
                                            "parą butów za dużych dla każdego"),
    "a compass that points a little east of north": ("kompas wskazujący trochę na wschód od północy", "kompas wskazujący trochę na wschód od północy",
                                                       "kompasu wskazującego trochę na wschód od północy", "kompasem wskazującym trochę na wschód od północy"),
    "a pencil worn to a nub": ("ołówek starty do końca", "ołówek starty do końca", "ołówka startego do końca", "ołówkiem startym do końca"),
    "boots": ("buty", "buty", "butów", "butami"),
    "a small keepsake": ("drobna pamiątka", "drobną pamiątkę", "drobnej pamiątki", "drobną pamiątką"),
}
# keepsakes: EN without article -> (nom, acc, gen, ins)
KEEPS = {
    "chessboard": ("szachownica", "szachownicę", "szachownicy", "szachownicą"),
    "guitar string": ("struna gitarowa", "strunę gitarową", "struny gitarowej", "struną gitarową"),
    "comic book": ("komiks", "komiks", "komiksu", "komiksem"),
    "teddy bear": ("pluszowy miś", "pluszowego misia", "pluszowego misia", "pluszowym misiem"),
    "pouch of seeds": ("woreczek nasion", "woreczek nasion", "woreczka nasion", "woreczkiem nasion"),
    "deck of cards": ("talia kart", "talię kart", "talii kart", "talią kart"),
    "harmonica": ("harmonijka", "harmonijkę", "harmonijki", "harmonijką"),
}
# weapons: EN -> (nom, acc, gen, ins)
WEAPONS = {
    "the bow": ("łuk", "łuk", "łuku", "łukiem"), "the revolver": ("rewolwer", "rewolwer", "rewolweru", "rewolwerem"), "the shorty": ("obrzyn", "obrzyn", "obrzyna", "obrzynem"),
    "the hunting rifle": ("karabin myśliwski", "karabin myśliwski", "karabinu myśliwskiego", "karabinem myśliwskim"),
    "the semi-auto rifle": ("karabin półautomatyczny", "karabin półautomatyczny", "karabinu półautomatycznego", "karabinem półautomatycznym"),
    "the burst rifle": ("karabin seryjny", "karabin seryjny", "karabinu seryjnego", "karabinem seryjnym"),
    "the 9mm": ("pistolet 9 mm", "pistolet 9 mm", "pistoletu 9 mm", "pistoletem 9 mm"),
    "the crossbow": ("kusza", "kuszę", "kuszy", "kuszą"),
    "a length of pipe": ("kawał rury", "kawał rury", "kawała rury", "kawałem rury"),
    "nail bombs": ("bomby gwoździowe", "bomby gwoździowe", "bomb gwoździowych", "bombami gwoździowymi"),
    "molotovs": ("koktajle Mołotowa", "koktajle Mołotowa", "koktajli Mołotowa", "koktajlami Mołotowa"),
}
PREV_RES = {"a win": "wygrana", "a loss": "porażka", "a plain day": "zwykły dzień"}
NTH = {"second": "po raz drugi", "third": "po raz trzeci", "fourth": "po raz czwarty", "fifth": "po raz piąty", "sixth": "po raz szósty", "seventh": "po raz siódmy",
       "again": "po raz kolejny"}
# numerals (nominative, masculine / feminine) and genitive
NUM_M = ["zero", "jeden", "dwa", "trzy", "cztery", "pięć", "sześć", "siedem", "osiem", "dziewięć", "dziesięć"]
NUM_F = ["zero", "jedna", "dwie", "trzy", "cztery", "pięć", "sześć", "siedem", "osiem", "dziewięć", "dziesięć"]
NUM_GEN = ["zera", "jednego", "dwóch", "trzech", "czterech", "pięciu", "sześciu", "siedmiu", "ośmiu", "dziewięciu", "dziesięciu"]

# accusative of the feminine singular groups above (everything else: accusative = nominative)
ACC = {
    "zwalona jodła nad potokiem": "zwaloną jodłę nad potokiem", "ambona myśliwska": "ambonę myśliwską", "ścieżka jeleni": "ścieżkę jeleni", "spalona chata": "spaloną chatę",
    "wysepka z dystrybutorami": "wysepkę z dystrybutorami", "alejka z lodówkami": "alejkę z lodówkami", "sala gimnastyczna": "salę gimnastyczną",
    "wschodnia klatka schodowa": "wschodnią klatkę schodową", "stołówka": "stołówkę", "pętla autobusowa": "pętlę autobusową", "kabina dźwigu": "kabinę dźwigu",
    "spawalnia": "spawalnię", "szopa na wózki golfowe": "szopę na wózki golfowe", "cysterna": "cysternę", "sala modlitw": "salę modlitw", "wędzarnia": "wędzarnię",
    "tkalnia": "tkalnię", "zakratowana apteka": "zakratowaną aptekę", "rampa załadunkowa": "rampę załadunkową", "recepcja": "recepcję", "wieża ciśnień": "wieżę ciśnień",
    "piekarnia": "piekarnię", "ślepa uliczka": "ślepą uliczkę", "piwnica przychodni": "piwnicę przychodni", "hala studia": "halę studia", "reżyserka": "reżyserkę",
    "garderoba": "garderobę", "hala biletowa": "halę biletową", "przechowalnia bagażu": "przechowalnię bagażu", "nastawnia": "nastawnię", "kładka": "kładkę",
    "wielka sala": "wielką salę", "szopa na łodzie": "szopę na łodzie", "sala trofeów": "salę trofeów", "długa weranda": "długą werandę",
    "kuchnia z oknem wykuszowym": "kuchnię z oknem wykuszowym", "lada kawiarni": "ladę kawiarni", "galeria na piętrze": "galerię na piętrze", "witryna": "witrynę",
    "brama": "bramę", "serpentyna": "serpentynę", "kaplica": "kaplicę", "pralnia samoobsługowa": "pralnię samoobsługową", "tylna uliczka": "tylną uliczkę",
    "hala wystawowa": "halę wystawową", "kładka techniczna": "kładkę techniczną", "bariera ochronna": "barierę ochronną", "budka poborcy opłat": "budkę poborcy opłat",
    "główna hala": "główną halę", "następna mapa": "następną mapę", "stacja benzynowa": "stację benzynową", "szkoła": "szkołę", "stocznia": "stocznię",
    "stacja telewizyjna": "stację telewizyjną", "leśniczówka": "leśniczówkę", "księgarnia": "księgarnię", "stołówka bazy": "stołówkę bazy",
    "stara sala gimnastyczna": "starą salę gimnastyczną", "chata w przystani": "chatę w przystani", "mapa ": "mapę ",
}
