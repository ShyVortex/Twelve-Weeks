"""A-Life text pools, part A: expeditions, injuries (light duty), building projects.  Each row: (scope, tone, English, Polish).
scope "*" | "W" (Wolves / WLF) | "S" (Seraphites);  tone "*" any morale, "g" good (morale >= 55), "n" middle (35..70), "b" bad (<= 45).
Placeholders and the Polish switches: see tools/clan_alife_lex.py.  Pool contracts (letters / variables the engine provides) are in clan_alife.py."""

POOLS = {}

# ---- an expedition leaves: A leads, B follows, C (optional) too; dest, goal, nd (days it will take; nd_in)
POOLS["exp_leave"] = [
    ("W", "*", "{A}, {B} and {C} take the long way round to {dest}. They want {goal}, and they will be back {nd_in}.",
     "{A}, {B} i {C} idą okrężną drogą {dest_to}. Szukają {goal_gen} i wrócą {nd_in}."),
    ("*", "*", "{A} draws the route to {dest} on a scrap of cardboard; {B} gets a copy. They are gone by noon.",
     "{A} rysuje na kartonie trasę {dest_to}; {B} dostaje kopię. Przed południem już ich nie ma."),
    ("*", "*", "{A} swears you can still find {goal} at {dest}, and {B} goes along to see it with {B_his} own eyes.",
     "{A} przysięga, że {dest_at} wciąż można znaleźć {goal_acc}, a {B} idzie to sprawdzić na własne oczy."),
    ("*", "b", "Nobody wants to go to {dest} this week, so {A} and {B} draw lots and lose. They leave for {goal} with long faces.",
     "Nikt nie chce iść {dest_to} w tym tygodniu, więc {A} i {B} ciągną losy i przegrywają. Wyruszają po {goal_acc} z kwaśnymi minami."),
    ("*", "g", "{A} and {B} leave with a song on their lips, the kind of morning that makes a long walk to {dest} feel short. They are after {goal}.",
     "{A} i {B} wychodzą z piosenką na ustach, w taki poranek długi marsz {dest_to} wydaje się krótki. Chodzi o {goal_acc}."),
    ("W", "*", "Isaac wants {goal} found. {A} and {B} take the job and set off for {dest}.",
     "Isaac chce, żeby ktoś znalazł {goal_acc}. {A} i {B} biorą to zadanie i ruszają {dest_to}."),
    ("S", "*", "The Prophet's word is that the island needs {goal}. {A} and {B} set out for {dest} before the tide turns.",
     "Słowo Proroka mówi, że wyspa potrzebuje {goal_gen}. {A} i {B} ruszają {dest_to}, zanim zmieni się pływ."),
    ("W", "*", "{A}, {B} and {C} leave in single file, rifles low. {dest} first, then {goal}, then home.",
     "{A}, {B} i {C} wychodzą gęsiego z opuszczonymi karabinami. Najpierw {dest}, potem {goal}, potem dom."),
    ("S", "*", "{A}, {B} and {C} leave in single file, bows unstrung until the shore is behind them. {dest}, then {goal}, then home.",
     "{A}, {B} i {C} wychodzą gęsiego, łuki nienapięte, dopóki brzeg nie zostanie za nimi. Najpierw {dest}, potem {goal}, potem dom."),
]

# ---- the party is still out (A stays in camp, B is away): dest, nd = days gone so far (nd_ago)
POOLS["exp_wait"] = [
    ("*", "*", "{B} left for {dest} {nd_ago}. {A} has stopped pretending not to watch the gate.",
     "{B} wyruszył{B?|a} {dest_to} {nd_ago}. {A} przestał{A?|a} udawać, że nie patrzy na bramę."),
    ("*", "*", "{A} leaves a lamp lit in the window for {B}. {B} is still out at {dest}.",
     "{A} zostawia w oknie zapaloną lampę dla {B?niego|niej}. {B} wciąż jest {dest_at}."),
    ("W", "b", "There has been no word from {B} since {B_he} left. {A} says it is the radio. Nobody believes it is the radio.",
     "{B} {B?wyszedł|wyszła}, a od tamtej pory nie ma żadnych wieści. {A} mówi, że to radio. Nikt nie wierzy, że to radio."),
    ("S", "b", "There has been no word from {B} since {B_he} left. {A} says the tide is late. Nobody believes it is the tide.",
     "{B} {B?wyszedł|wyszła}, a od tamtej pory nie ma żadnych wieści. {A} mówi, że to przez pływ. Nikt nie wierzy, że to przez pływ."),
    ("*", "*", "{A} asks the gate watch twice an hour whether {B} is back from {dest} yet.",
     "{A} co godzinę pyta wartę przy bramie, czy {B} już wrócił{B?|a} {dest_from}."),
    ("*", "g", "Supper is kept warm for {B}, who should be back from {dest} by now. {A} tells everyone not to worry, in a voice that is not worried.",
     "Ktoś trzyma ciepłą kolację: {B} powin{B?ien|na} być już z powrotem {dest_from}. {A} mówi wszystkim, żeby się nie martwili, głosem, który się nie martwi."),
]

# ---- the party is back with the goods: A, B, (C), dest, goal, nd (days it took: nd_after)
POOLS["exp_ret_good"] = [
    ("*", "*", "{A} and {B} are back from {dest} {nd_after}, loaded down with {goal}. Nobody asks how it went; the bags say enough.",
     "{A} i {B} wracają {dest_from} {nd_after}, obładowani {goal_ins}. Nikt nie pyta, jak poszło; torby mówią same za siebie."),
    ("*", "*", "The party comes home from {dest} {nd_after} with {goal}. {A} sets the haul on the table and counts it twice.",
     "Grupa wraca {dest_from} {nd_after} {goal_with}. {A} kładzie łup na stole i liczy go dwa razy."),
    ("W", "*", "The quartermaster signs for {goal}: {A} and {B} came back from {dest} with more than anyone expected.",
     "Kwatermistrz kwituje {goal_acc}: {A} i {B} wróci{AB?li|ły} {dest_from} z większym łupem, niż ktokolwiek się spodziewał."),
    ("S", "*", "{A} and {B} come up the beach at dusk, bent under sacks of {goal}. The long house hums with it all evening.",
     "{A} i {B} docierają o zmierzchu na plażę, zgięci pod workami {goal_gen}. Cały wieczór długi dom huczy od tej wieści."),
    ("*", "g", "{A} grins the whole walk back from {dest}. {B} tells the story of getting the {goal} three times before supper.",
     "{A} szczerzy zęby przez całą drogę {dest_from}. Historię zdobycia {goal_gen} {B} opowiada trzy razy przed kolacją."),
    ("*", "*", "{A} was right about {dest}: they came back with {goal}. {B} is already asking when they can go again.",
     "{A} miał{A?|a} rację co do {dest_gen}: wrócili {goal_with}. {B} już pyta, kiedy mogą iść znowu."),
    ("*", "b", "It was not much, but {A} and {B} came back from {dest} with {goal}, and tonight that counts.",
     "To niewiele, ale {A} i {B} wróci{AB?li|ły} {dest_from} {goal_with} i dziś to się liczy."),
    ("*", "n", "{A} drops a heavy bag by the door: {goal}, from {dest}. {B} follows with a second bag and a story about a dog that tracked them half the way.",
     "{A} rzuca przy drzwiach ciężką torbę {goal_with} {dest_from}. {B} wchodzi za {A?nim|nią} z drugą torbą i historią o psie, który szedł za nimi pół drogi."),
    ("W", "*", "{A} comes through the gate with {goal} from {dest} and a look that says do not ask about the route.",
     "{A} wchodzi przez bramę {goal_with} {dest_from} i miną, która mówi: nie pytajcie o trasę."),
    ("S", "*", "The weavers clear a place on the long table for {goal} from {dest}; {A} and {B} are given the first bowls of broth.",
     "Tkacze robią miejsce na długim stole na {goal_acc} {dest_from}; {A} i {B} dostają pierwsze miski zupy."),
]

# ---- the party is back with nothing
POOLS["exp_ret_empty"] = [
    ("*", "*", "{A} and {B} are back from {dest} {nd_after} with nothing. The shelves were bare, and somebody had been there first.",
     "{A} i {B} wracają {dest_from} {nd_after} z pustymi rękami. Półki były gołe, ktoś ich uprzedził."),
    ("*", "*", "Nothing at {dest}. {A} says it twice, as if the second time might change it, and goes to wash.",
     "Nic {dest_at}. {A} powtarza to dwa razy, jakby za drugim razem mogło się zmienić, i idzie się umyć."),
    ("*", "b", "{A} and {B} found no {goal}. They found an empty can and one more reason to be tired.",
     "{A} i {B} nie znaleźli {goal_gen}. Znaleźli pustą puszkę i jeszcze jeden powód do zmęczenia."),
    ("*", "*", "The trip to {dest} for {goal} came to nothing. {B} swears the place was picked clean a week ago.",
     "Wyprawa {dest_to} po {goal_acc} spełzła na niczym. {B} przysięga, że miejsce ogołocono tydzień temu."),
    ("*", "n", "The map comes back from {dest} with one more crossing-out. {A} and {B} are home {nd_after}, without {goal}.",
     "Mapa wraca z jednym skreśleniem więcej: {dest}. {A} i {B} są w domu {nd_after}, bez {goal_gen}."),
    ("S", "*", "The tide took the path to {dest}. {A} and {B} turn back with wet boots and no {goal}.",
     "Przypływ zabrał drogę {dest_to}. {A} i {B} zawracają z mokrymi butami i bez {goal_gen}."),
    ("W", "*", "Scrappers had been through {dest} before them. {A} and {B} come back with a bent spoon and bad words.",
     "Szabrownicy byli {dest_at} przed nimi. {A} i {B} wracają z wygiętą łyżką i brzydkimi słowami."),
]

# ---- back, and A is hurt (a minor injury: light duty, NOT sickness): A hurt, B well, inj, goal, dest
POOLS["exp_ret_hurt"] = [
    ("*", "*", "{B} helps {A} home from {dest}. {A_He} has {inj}, but the {goal} made it back.",
     "{B} pomaga {A?mu|jej} wrócić {dest_from}. {A} ma {inj_acc}, ale udało się przynieść {goal_acc}."),
    ("*", "*", "Back from {dest} with {goal}, and with {inj} for {A}. Rest will fix it, everyone agrees, which is what people say when they do not know.",
     "Wracają {dest_from} {goal_with}, a {A} ma {inj_acc}. Odpoczynek to naprawi, zgadzają się wszyscy, czyli tak, jak się mówi, kiedy się nie wie."),
    ("*", "*", "A bad fall at {dest}: {A} has {inj}. Still, {B} carries the {goal} home in {A}'s coat.",
     "Niefortunny upadek {dest_at}: {A} ma {inj_acc}. Mimo to {B} niesie {goal_acc} w {A?jego|jej} płaszczu."),
    ("W", "*", "{A} has {inj} after a clicker got too close at {dest}. {B} still got the {goal} out.",
     "{A} ma {inj_acc} po bliskim spotkaniu z klikaczem {dest_at}. {B} zdołał{B?|a} jednak wynieść {goal_acc}."),
    ("S", "*", "A slick rock at {dest} and a wet fall: {A} has {inj}. {B} carries the {goal} the rest of the way, saying nothing, which is its own kind of kindness.",
     "Śliski kamień {dest_at} i mokry upadek: {A} ma {inj_acc}. {B} niesie {goal_acc} do końca drogi, nic nie mówiąc, co też jest formą życzliwości."),
]

# ---- back, and they met the other faction: enemy / enemies come from the faction
POOLS["exp_ret_contact"] = [
    ("*", "*", "{A} and {B} saw a {enemy} patrol at {dest} and lay still in the dark until it passed. The {goal} will have to wait.",
     "{A} i {B} zobaczy{AB?li|ły} patrol {enemy_gen} {dest_at} i le{AB?żeli|żały} bez ruchu w ciemności, aż przeszedł. Po {goal_acc} pójdą innym razem."),
    ("*", "*", "Fresh boot prints around {dest}: the {enemies} are looking for the same thing. {A} and {B} come home early and say little about how close it was.",
     "Świeże ślady butów wokół {dest_gen}: {enemy} szukają tego samego. {A} i {B} wracają wcześniej i niewiele mówią o tym, jak blisko było."),
    ("*", "n", "{A} traded a lighter for {goal} with a lone {enemy} scout at {dest}, who did not want the shooting either. Nobody says that out loud.",
     "{A} wymienił{A?|a} zapalniczkę na {goal_acc} z samotnym zwiadowcą {enemy_gen} {dest_at}, który też nie chciał strzelaniny. Nikt nie mówi tego na głos."),
    ("*", "b", "Gunfire at {dest}. {A} and {B} get out through a drain and come back without the {goal}, shaking.",
     "Strzelanina {dest_at}. {A} i {B} uciekają kanałem i wracają bez {goal_gen}, dygocząc."),
]

# ---- back, and an infected nearly ended it
POOLS["exp_ret_inf"] = [
    ("*", "*", "A {inf} was waiting in the dark at {dest}. {A} and {B} back out the way they came, quietly, and will try for {goal} somewhere else.",
     "{dest_at} w ciemności czekał {inf}. {A} i {B} wycofują się tą samą drogą, po cichu, i spróbują po {goal_acc} gdzie indziej."),
    ("*", "*", "{A} counts {infs} at {dest}: too many for two people. {B} wants to go in anyway. They do not, and nobody calls it cowardice.",
     "{A} nalicza {infs_gen} {dest_at}: za dużo jak na dwie osoby. {B} i tak chce wejść. Nie wchodzą i nikt nie nazywa tego tchórzostwem."),
    ("*", "*", "{A} and {B} are back from {dest} with the {goal}, and with a story: a {inf}, a locked door, and a very short sprint.",
     "{A} i {B} wracają {dest_from} {goal_with} i z historią: {inf}, zamknięte drzwi i bardzo krótki sprint."),
]

# ---- the party came back short: A leads the rest, D did not come back (story cause: lost / walked away), dest
POOLS["exp_lost"] = [
    ("*", "*", "{A} says the party lost {D} near {dest}. It was quick, {A_he} says, and says it again, as if saying it enough would make it true.",
     "{A} mówi, że w pobliżu {dest_gen} grupa straciła kogoś: {D}. Stało się to szybko, mówi {A}, i mówi to jeszcze raz, jakby wystarczająco częste powtarzanie miało uczynić to prawdą."),
    ("*", "*", "The party came back from {dest} one short. The pack {D} carried sits by the door, and nobody touches it.",
     "Grupa wróciła {dest_from} w mniejszym składzie. Plecak, który nosi{D?ł|ła} {D}, stoi przy drzwiach i nikt go nie rusza."),
    ("*", "b", "{A} tries to explain what happened to {D} at {dest} and gives up halfway through the sentence.",
     "{D}: {A} próbuje wyjaśnić, co stało się {dest_at}, i rezygnuje w połowie zdania."),
]

# ---- a party member fell ill or the clan was starving while out: the party is recalled (A leads, B sick or hungry now)
POOLS["exp_recall"] = [
    ("*", "*", "{A} cuts the trip to {dest} short: {B} is not fit to walk any farther, and {A} will not leave {B_him} behind.",
     "{A} skraca wyprawę {dest_to}: {B} nie da rady iść dalej, a {A} nie zostawi {B?go|jej} samego."),
    ("*", "*", "The party turns back from {dest} before it has found {goal}. {B} is struggling, and {A} makes the call.",
     "Grupa zawraca {dest_from}, zanim znalazła {goal_acc}. {B} ledwo idzie, a decyzję podejmuje {A}."),
]

# ---- injuries on light duty: A hurt (healthy, NOT sick), inj
POOLS["inj_mid"] = [
    ("*", "*", "{A} is on light duty with {inj}: sorting jars, mending coats and offering opinions nobody asked for.",
     "{A} ma lekką służbę z powodu {inj_gen}: sortuje słoiki, łata płaszcze i rozdaje opinie, o które nikt nie prosił."),
    ("*", "*", "{A} still has {inj}, better than yesterday. {A_He} will not admit it hurts.",
     "{A} wciąż ma {inj_acc}, ale lepiej niż wczoraj. {A?On|Ona} nie przyzna, że boli."),
    ("*", "n", "{A} sits by the fire with {inj} and a pile of work that can be done sitting down.",
     "{A} siedzi przy ogniu {inj_with} i stosem roboty, którą da się wykonać na siedząco."),
    ("*", "g", "{A} jokes about {inj} all through supper. {B} laughs, and then carries {A}'s bowl without being asked.",
     "{A} żartuje na temat {inj_gen} przez całą kolację. {B} się śmieje, a potem bez proszenia niesie {A?jego|jej} miskę."),
    ("*", "b", "{A} says it is nothing. {A_He} has now said so four times today, and nobody believes it.",
     "{A} mówi, że to nic. Powtórzył{A?|a} to dziś już cztery razy i nikt w to nie wierzy."),
]
POOLS["inj_heal"] = [
    ("*", "*", "{A} no longer has {inj} and goes back on the rota. The others pretend they never doubted it.",
     "{A} nie ma już {inj_gen} i wraca do grafiku. Reszta udaje, że nigdy nie wątpiła."),
    ("*", "g", "{A} is back to full work today. {B} makes a show of handing over the heavy end of the load.",
     "{A} wraca dziś do pełnej pracy. {B} demonstracyjnie oddaje {A?mu|jej} cięższy koniec ciężaru."),
]

# ---- building: A leads, B helps, proj; prog bucket
POOLS["proj_start"] = [
    ("*", "*", "{A} stakes out the ground for {proj}. {B} gets the shovel and a doubtful look.",
     "{A} wyznacza miejsce pod {proj_acc}. {B} dostaje łopatę i niepewną minę."),
    ("*", "*", "The plans for {proj} come out of a drawer, stained and folded in eight. {A} reads them aloud; {B} nods as if they made sense.",
     "Plany {proj_gen} wychodzą z szuflady, poplamione i złożone w ósemkę. {A} czyta je na głos, a {B} kiwa głową, jakby miały sens."),
    ("S", "*", "After the evening reading, {A} stands and announces work on {proj}. The whole long house hears it; {B} is the first to offer {B_his} hands.",
     "Po wieczornym czytaniu {A} wstaje i zapowiada prace nad {proj_ins}. Cały długi dom to słyszy; {B} pierwsz{B?y|a} ofiarowuje swoje ręce."),
    ("W", "*", "Isaac signs off on {proj}. {A} gets the job and {B} gets whatever is left of the manpower and the sleep.",
     "Isaac zatwierdza prace nad {proj_ins}. {A} dostaje to zadanie, a {B} to, co zostanie z ludzi i ze snu."),
    ("*", "n", "Work on {proj} starts today. {A} and {B} argue about the first nail for a good ten minutes, which everybody agrees is a good sign.",
     "Dziś ruszają prace nad {proj_ins}. {A} i {B} kłócą się o pierwszy gwóźdź dobre dziesięć minut, co wszyscy uznają za dobry znak."),
    ("*", "b", "Nobody has the strength, but {proj} cannot wait. {A} starts alone; after an hour {B} comes out and picks up the other end.",
     "Nikt nie ma siły, ale prace nad {proj_ins} nie mogą czekać. {A} zaczyna sam{A?|a}; po godzinie wychodzi {B} i chwyta drugi koniec."),
    ("*", "g", "Spirits are up, so {A} picks the day to begin {proj}. {B} brings tea for the diggers before they have dug anything.",
     "Nastroje są dobre, więc {A} wybiera ten dzień na początek prac nad {proj_ins}. {B} przynosi herbatę dla kopaczy, zanim cokolwiek wykopią."),
]
POOLS["proj_prog"] = [
    ("*", "n", "{B} measures twice and tells {A} the whole thing is crooked. {A} measures once and says it is not. The work is {prog}.",
     "{B} mierzy dwa razy i mówi {A?mu|jej}, że to krzywe. {A} mierzy raz i mówi, że nie. Prace nad {proj_ins} {prog}."),
    ("S", "*", "The work on {proj} goes on between prayers and meals. {A} and {B} take the day shift; the work is {prog}.",
     "Prace nad {proj_ins} toczą się między modlitwą a posiłkami. {A} i {B} mają zmianę dzienną; prace {prog}."),
    ("W", "*", "{A} and {B} scrounge nails from the old fence for {proj}. The work is {prog}, and the fence is not looking good.",
     "{A} i {B} wyciągają gwoździe ze starego ogrodzenia na potrzeby prac nad {proj_ins}. Prace {prog}, a ogrodzenie nie wygląda dobrze."),
]
POOLS["proj_stall"] = [
    ("*", "*", "Work on {proj} stops: {A} and {B} are out looking for food instead.",
     "Prace nad {proj_ins} stanęły: {A} i {B} zamiast tego szukają jedzenia."),
    ("*", "b", "The tools for {proj} lie where they were dropped. {A} says they will pick them up tomorrow, when there is something in their stomachs.",
     "Narzędzia do prac nad {proj_ins} leżą tam, gdzie je rzucono. {A} mówi, że podniosą je jutro, kiedy coś będą mieli w brzuchach."),
    ("*", "*", "{B} covers {proj} with a tarp and sets a stone on every corner. It will keep until there is something to eat.",
     "{B} przykrywa {proj_acc} plandeką i kładzie kamień na każdym rogu. Poczeka, aż będzie co jeść."),
]
POOLS["proj_done"] = [
    ("*", "*", "The work on {proj} is finished. {A} steps back, wipes {A_his} hands and says nothing, which is the highest praise {A_he} knows.",
     "Koniec prac nad {proj_ins}. {A} odsuwa się o krok, ociera dłonie i nic nie mówi, a to najwyższa pochwała, jaką zna."),
    ("*", "g", "The work on {proj} is done, and {B} insists on a toast with the last of the tea. {A} accepts, modestly, twice.",
     "Prace nad {proj_ins} skończone; {B} nalega na toast resztką herbaty. {A} przyjmuje go skromnie, dwa razy."),
    ("*", "n", "{A} nails the last board in the work on {proj}. The first thing anyone does with it is lean on it, to be sure.",
     "{A} przybija ostatnią deskę w ramach prac nad {proj_ins}. Pierwsze, co robi każdy, to oprzeć się o nią, żeby się upewnić."),
    ("*", "b", "Against all odds, the work on {proj} is finished. Nobody cheers; people just stand and look at it for a while.",
     "Wbrew wszelkim szansom prace nad {proj_ins} są skończone. Nikt nie wiwatuje; ludzie po prostu stoją i patrzą na to przez chwilę."),
]
