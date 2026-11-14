"""Text bank of the clan chronicle (tools/clan_chronicle.py): EN + PL side by side.

Row format: (scope, tone, en, pl)   scope "*" both factions | "W" WLF only | "S" Seraphites only;  tone "*" | "g" good day | "b" bad day | "n" neutral.
People: {A} the person in focus, {B} their bond partner, {C} a third survivor, {D} the dead.  English pronouns {A_he} {A_his} {A_him}; Polish uses switches
{A?on|ona} and past endings {A?ł|ła} (whole-word switches where the stem changes: {A?kiwnął|kiwnęła}).
Variables: {map} {sup} {need} {kills} {deaths} {downs} {n} {enemy} {enemies} {leader} {wd} {gain}; Polish also {enemy_gen} {enemy_ins} {wd_acc}.
Every sentence of the first piece of a row (the headline) is kept under ~118 characters where it can, so the in-game one-line widget shows it whole.
"""

POOLS = {}

# ----------------------------------------------------------------------------------------------------------------- what the match brought home
POOLS["match_strong"] = [
    ("W", "g", "The line held on {map}: {kills} of {enemies} down for {deaths} of ours. {A} reads the tally aloud twice, like it might change.",
     "Linia na mapie {map} wytrzymała: {kills} po ich stronie, {deaths} po naszej. {A} czyta wynik na głos dwa razy, jakby miał się zmienić."),
    ("W", "g", "Word from {map}: {kills} down on their side, {deaths} on ours. {leader} calls it a clean day. {A} calls it a lucky one, and writes both.",
     "Wieści z mapy {map}: {kills} po ich stronie, {deaths} po naszej. {leader} mówi, że czysty dzień. {A} mówi, że szczęśliwy, i zapisuje oba."),
    ("S", "g", "The Prophet walked with us on {map}: {kills} of {enemies} fallen, {deaths} of our own. {A} says the count, and then the names of the dead we did not have.",
     "Prorok szedł z nami na mapie {map}: {kills} poległych po ich stronie, {deaths} po naszej. {A} mówi liczbę, a potem imiona tych, których nie straciliśmy."),
    ("S", "g", "{map} was ours: {kills} of {enemies}, {deaths} lost. The children are told it was the Sisters' prayers. {A} lets them believe it.",
     "Mapa {map} była nasza: {kills} z {enemy_gen}, {deaths} strat. Dzieciom mówią, że to modlitwy Sióstr. {A} pozwala im w to wierzyć."),
    ("*", "g", "You came back from {map} with {kills} of theirs and not a scratch on the count. {A} pours the first cup before anyone asks.",
     "Z mapy {map} wrócono z {kills} po ich stronie i bez rysy w rachunku. {A} nalewa pierwszy kubek, zanim ktokolwiek poprosi."),
]
POOLS["match_even"] = [
    ("*", "n", "{map}: {kills} of theirs, {deaths} of ours. {A} writes it down in pencil, because nobody is sure yet what it was worth.",
     "{map}: {kills} ich, {deaths} naszych. {A} zapisuje to ołówkiem, bo nikt jeszcze nie wie, ile to było warte."),
    ("W", "n", "Back from {map}. {kills} on their side, {deaths} on ours, and {downs} close calls nobody wants to talk about. {A} counts the magazines instead.",
     "Powrót z mapy {map}. {kills} po ich stronie, {deaths} po naszej i {downs} razy o włos, o czym nikt nie chce mówić. {A} liczy zamiast tego magazynki."),
    ("S", "n", "{map} gave and took: {kills} of {enemies}, {deaths} of ours, and {downs} falls we got up from. {A} says that is what the Sisters call a fair price.",
     "Mapa {map} dała i zabrała: {kills} z {enemy_gen}, {deaths} naszych i {downs} upadków, z których wstaliśmy. {A} mówi, że Siostry nazywają to uczciwą ceną."),
    ("*", "n", "It was a long one on {map}. {kills} down, {deaths} lost. {A} sits on the steps and takes {A_his} boots off like they weigh more than they should.",
     "To była długa runda na mapie {map}. {kills} trafionych, {deaths} strat. {A} siada na schodach i zdejmuje buty, jakby ważyły więcej, niż powinny."),
]
POOLS["match_bad"] = [
    ("W", "b", "{map} went badly: {deaths} of ours down for {kills} of {enemies}. {A} will not look at the roster, and {B} stands next to {A_him} until {A} does.",
     "Na mapie {map} poszło źle: {deaths} naszych poległych za {kills} po ich stronie. {A} nie chce patrzeć na listę, a {B} stoi obok, aż spojrzy."),
    ("S", "b", "{map} took more than it gave: {deaths} of ours against {kills} of {enemies}. {A} prays in the long house with the door open, so we can all hear it is only {A_him} shaking.",
     "Mapa {map} zabrała więcej, niż dała: {deaths} naszych wobec {kills} z {enemy_gen}. {A} modli się w długim domu przy otwartych drzwiach, żebyśmy wszyscy słyszeli, że to tylko {A?on|ona} drży."),
    ("*", "b", "{deaths} down on {map}, and only {kills} of theirs to show for it. Nobody argues about the numbers tonight. Nobody argues about anything.",
     "{deaths} poległych na mapie {map}, a po ich stronie tylko {kills}. Dziś nikt nie kłóci się o liczby. Nikt się o nic nie kłóci."),
    ("*", "b", "You were put on the ground {downs} times on {map}, and every time somebody had to pull you up. {A} says that is no way to keep a clan.",
     "Na mapie {map} {downs} razy kładziono cię na ziemię i za każdym razem ktoś musiał cię podnosić. {A} mówi, że tak się klanu nie prowadzi."),
]
POOLS["match_downs"] = [
    ("*", "*", "{A} heard you went down {downs} times on {map} and still got up. No well done from {A}, only an extra blanket on your bunk.",
     "{A} słyszał{A?|a}, że na mapie {map} powalono cię {downs} razy, a mimo to wróciło się na własnych nogach. Nie mówi brawo. Kładzie ci na pryczy dodatkowy koc."),
    ("W", "*", "{downs} times down on {map}. {A} the {A_role} runs {A_his} fingers over your vest like a tailor, counting what the plates took.",
     "{downs} razy na ziemi na mapie {map}. {A}, {A_role}, przesuwa palcami po twojej kamizelce jak krawiec, licząc, co przyjęły płyty."),
    ("S", "*", "{downs} falls on {map}, and each time the Sisters say you rose. {A} the {A_role} says it is not a miracle, only a stubborn spine.",
     "{downs} upadków na mapie {map}, a po każdym, jak twierdzą Siostry, coś cię podnosiło. {A}, {A_role}, twierdzi, że to nie cud, tylko uparty kręgosłup."),
]

# ----------------------------------------------------------------------------------------------------------------- supplies home
POOLS["haul_good"] = [
    ("W", "g", "{sup} supplies through the gate against {need} needed. {A} chalks the number on the wall, then wipes it off, so the Scars cannot read it.",
     "{sup} zapasów przez bramę przy potrzebnych {need}. {A} pisze liczbę kredą na ścianie, po czym ją ściera, żeby Blizny jej nie przeczytały."),
    ("W", "g", "The crates come in at {sup} and the quartermaster {A} lets nobody touch them until they are counted. The mess is full of men pretending not to look.",
     "Skrzynie przychodzą w liczbie {sup}, a kwatermistrz {A} nie pozwala ich tknąć, póki nie zostaną przeliczone. Stołówka pełna ludzi udających, że nie patrzą."),
    ("S", "g", "{sup} baskets of supplies for {need} mouths. {A} gives the thanks aloud, in the old words, and the children repeat them with their mouths full.",
     "{sup} koszy zapasów na {need} gąb. {A} dziękuje na głos, starymi słowami, a dzieci powtarzają je z pełnymi buziami."),
    ("S", "g", "The harvest of your hands is {sup}, and we needed {need}. {A} says the surplus belongs to whoever is hungriest, and walks it to {B} first.",
     "Plon waszych rąk to {sup}, a potrzebowaliśmy {need}. {A} mówi, że nadwyżka należy do najbardziej głodnych, a pierwsza porcja trafia tam, gdzie siedzi {B}."),
    ("*", "g", "{sup} in, {need} out. For the first time this week the soup has something in it that used to be alive.",
     "{sup} wchodzi, {need} wychodzi. Pierwszy raz w tym tygodniu w zupie jest coś, co kiedyś żyło."),
    ("*", "g", "More than enough: {sup} against {need}. {A} laughs once, short, and covers {A_his} mouth, as if the laugh itself might be rationed.",
     "Z nawiązką: {sup} przy {need}. {A} śmieje się raz, krótko, i zakrywa usta, jakby sam śmiech mógł być na kartki."),
]
POOLS["haul_short"] = [
    ("W", "b", "{sup} supplies in, {need} needed. {A} reads the gap to the barracks as an order of the day. Nobody cheers, nobody complains, and that is worse.",
     "{sup} zapasów, potrzeba {need}. {A} odczytuje różnicę w koszarach jak rozkaz dzienny. Nikt się nie cieszy, nikt nie narzeka, a to gorzej."),
    ("W", "b", "We are {n} short today. {A} splits the crates by the roster, and takes the smallest share {A_himself}, and pretends it was an accident.",
     "Brakuje dziś {n}. {A} dzieli skrzynie według listy i bierze najmniejszą porcję dla siebie, udając, że to przypadek."),
    ("S", "b", "{sup} against {need}: the baskets are light. {A} counts the grains aloud in the long house, so nobody can say later that we were not fair.",
     "{sup} przy {need}: kosze są lekkie. {A} liczy ziarna na głos w długim domu, żeby nikt potem nie mógł powiedzieć, że nie byliśmy sprawiedliwi."),
    ("S", "b", "The Prophet's table is thin tonight: {sup} for {need}. {A} serves the children first and eats last, in the manner of the elders.",
     "Stół Proroka jest dziś chudy: {sup} na {need}. {A} obsługuje dzieci pierwsze i je ostatni, jak przystało starszym."),
    ("*", "b", "Not enough: {sup} for {need}. {A} puts a lid on the pot to keep the smell in, and the hunger out of everyone's faces.",
     "Za mało: {sup} na {need}. {A} przykrywa garnek pokrywką, żeby zatrzymać zapach, a głód wyprowadzić z twarzy."),
]
POOLS["ration"] = [
    ("*", "b", "Rations cut by a spoon each. {A} measures them with {A_his} own ladle and lets the others see {A_him} do it.",
     "Racje mniejsze o łyżkę na głowę. {A} odmierza je własną chochlą i pozwala, żeby wszyscy to widzieli."),
    ("W", "b", "{A} posts the new ration card on the mess door. By lunch somebody has drawn a small, bitter face on it. {A} leaves it up.",
     "{A} wiesza nową kartę racji na drzwiach stołówki. Do obiadu ktoś narysował na niej małą, gorzką buźkę. {A} zostawia ją."),
    ("S", "b", "At the evening meal {A} stands and asks who will give up their second bread. Hands rise slowly, then all at once, and {B} is the first to stand.",
     "Na wieczornym posiłku {A} wstaje i pyta, kto odda drugi chleb. Ręce unoszą się powoli, potem wszystkie naraz, a {B} wstaje {B?pierwszy|pierwsza}."),
    ("*", "g", "{A} proposes bringing the full ration back tomorrow. {B} says it is too early to hope. {A} says it is never too early to eat.",
     "{A} proponuje przywrócić jutro pełną rację. {B} mówi, że za wcześnie na nadzieję. {A} odpowiada, że nigdy nie jest za wcześnie na jedzenie."),
]

# ----------------------------------------------------------------------------------------------------------------- next raid
POOLS["raid_prep"] = [
    ("W", "*", "Briefing at dusk: the next push is {when}. {A} the {A_role} hands out the route on a torn map and asks that it be burned after it is read.",
     "Odprawa o zmierzchu: kolejne natarcie {when}. {A}, {A_role}, rozdaje trasę na podartej mapie i prosi, by po przeczytaniu ją spalić."),
    ("W", "*", "{leader} wants the line ready {when}. {A} drills the new ones on clearing a door until they stop flinching at the sound of it.",
     "{leader} chce mieć linię gotową {when}. {A} ćwiczy z nowymi wchodzenie przez drzwi, aż przestaną drgać na sam dźwięk."),
    ("S", "*", "The next crossing is {when}. {A} marks the path with three knots of cord and teaches the young ones to read them in the dark.",
     "Kolejne przejście jest {when}. {A} oznacza ścieżkę trzema węzłami sznurka i uczy młodych czytać je po ciemku."),
    ("S", "*", "Before the next hunt, {when}, the Sisters wash the weapons as if they were sleeping children. {A} sings under the cloth.",
     "Przed następnym polowaniem, {when}, Siostry obmywają broń jak śpiące dzieci. {A} śpiewa pod szmatką."),
    ("*", "*", "Everyone knows there is another fight coming. {A} sleeps in {A_his} boots, and nobody tells {A_him} to take them off.",
     "Wszyscy wiedzą, że zbliża się kolejna walka. {A} śpi w butach i nikt nie każe {A?mu|jej} ich zdjąć."),
    ("*", "*", "The next raid is {when}. {A} gives the kids their chores early, so there is something to hold on to when the adults go quiet.",
     "Kolejny wypad {when}. {A} rozdaje dzieciom obowiązki z wyprzedzeniem, żeby było się czego trzymać, gdy dorośli ucichną."),
]
POOLS["prep"] = [
    ("*", "*", "{B} sharpens the knives that will not be used, because the hands need work.", "{B} ostrzy noże, które się nie przydadzą, bo ręce potrzebują roboty."),
    ("*", "*", "{B} counts the rounds, then counts them again, then gives the box to {A} to count a third time.",
     "{B} liczy naboje, potem liczy jeszcze raz, potem oddaje pudełko, żeby {A} policzył{A?|a} po raz trzeci."),
    ("W", "*", "The vests are laid out by size on the barracks floor, like a row of men who have lain down for a minute.",
     "Kamizelki leżą w rzędzie na podłodze koszar według rozmiaru, jak ludzie, którzy położyli się na chwilę."),
    ("S", "*", "The arrows are fletched twice over tonight. {B} says feathers are cheaper than regret.",
     "Strzały są dziś opierzane dwa razy. {B} mówi, że pióra są tańsze niż żal."),
    ("*", "*", "The medic's bag is repacked twice: bandages on the left, the last two good needles on the right. {B} watches without a word.",
     "Torba medyczna jest pakowana dwa razy: bandaże po lewej, dwie ostatnie dobre igły po prawej. {B} patrzy bez słowa."),
    ("*", "*", "The water jugs are filled to the neck. Somebody has written a name on every lid, in case.",
     "Dzbany z wodą są napełnione po szyjkę. Ktoś napisał na każdej pokrywce imię, na wszelki wypadek."),
]

# ----------------------------------------------------------------------------------------------------------------- loss
POOLS["mourn"] = [
    ("W", "b", "We lost {D} today. The squad stood in the yard in the rain with caps in hand. {A} read the name from the roster and drew a line through it.",
     "{D?Odszedł|Odeszła} dziś {D}. Oddział stał na dziedzińcu w deszczu z czapkami w dłoniach. {A} odczytał{A?|a} imię z listy i przekreślił{A?|a} je."),
    ("S", "b", "{D} is gone. The Sisters washed {D?him|her} and wrapped {D?him|her} in white. {A} walks the shore until dark, saying the old words the wrong way round.",
     "{D} {D?odszedł|odeszła}. Siostry obmyły {D?go|ją} i owinęły w biel. {A} chodzi brzegiem do zmroku, mówiąc stare słowa na opak."),
    ("*", "b", "{D} did not wake up. {A} was the one who found {D?him|her}, and has not said a word since, only made tea for everyone, twice.",
     "{D} się nie obudził{D?|a}. To {A} {A?znalazł|znalazła} {D?go|ją}, i od tamtej pory nie powiedział{A?|a} słowa, tylko dwa razy zrobił{A?|a} wszystkim herbatę."),
    ("*", "b", "We buried {D} at the back, under the one tree that still has leaves. {B} planted {D?his|her} cup in the dirt, handle up, so it would be easy to find.",
     "Pochowaliśmy {D} z tyłu, pod jedynym drzewem, które ma jeszcze liście. {B} wbił{B?|a} {D?jego|jej} kubek w ziemię, uchem do góry, żeby łatwo go było znaleźć."),
]
POOLS["lastwords"] = [
    ("*", "b", "{D} left a note under the pillow. It says only: \"Don't let the little ones eat the last of the tins on my account.\" {A} reads it to the whole room.",
     "{D} zostawił{D?|a} kartkę pod poduszką. Jest na niej tylko: \"Nie pozwólcie maluchom zjeść ostatnich puszek z mojego powodu.\" {A} czyta ją całej izbie."),
    ("*", "b", "The last thing {D} said was a joke, and nobody laughed in time. {A} laughs now, a day late, on behalf of all of us.",
     "Ostatnią rzeczą, jaką powiedział{D?|a} {D}, był żart, i nikt nie zdążył się zaśmiać. {A} śmieje się teraz, dzień spóźniony, w imieniu nas wszystkich."),
    ("W", "b", "{D}'s last words on the radio were just the grid number, twice, then static. {A} still reads the number out at roll call.",
     "Ostatnie słowa, jakie {D} powiedział{D?|a} przez radio, to był tylko numer kwadratu, dwa razy, potem szum. {A} nadal odczytuje ten numer na apelu."),
    ("S", "b", "{D}'s last words were a verse we only half remember. {A} and {B} spend the evening arguing over the other half, and it feels like a prayer.",
     "Ostatnie słowa, które wypowiedział{D?|a} {D}, to był werset, który pamiętamy tylko w połowie. {A} i {B} spędzają wieczór, kłócąc się o drugą połowę, i to jest jak modlitwa."),
]

# ----------------------------------------------------------------------------------------------------------------- bodies and bellies
POOLS["sick_watch"] = [
    ("*", "b", "{A} is burning up and will not admit it. {B} sits by the bunk with a wet cloth and a bad joke, taking turns with both.",
     "{A} płonie w gorączce i nie chce się przyznać. {B} siedzi przy pryczy z mokrą szmatką i kiepskim dowcipem, na zmianę z jednym i drugim."),
    ("W", "b", "{A} is in the sick bay with a cough that carries across the yard. The medic says rest. {A} says the squad needs {A_him}. The medic locks the door.",
     "{A} leży w izbie chorych z kaszlem słychać na całym dziedzińcu. Medyk mówi: odpoczynek. {A} mówi, że oddział {A?go|ją} potrzebuje. Medyk zamyka drzwi na klucz."),
    ("S", "b", "{A} is feverish; the Sisters keep the lamp lit all night. {B} reads aloud from a book with no cover, whichever page falls open.",
     "{A} ma gorączkę; Siostry trzymają lampę zapaloną całą noc. {B} czyta na głos z książki bez okładki, na której stronie się otworzy."),
    ("*", "g", "{A} is up and walking the yard, thin as a rake. {B} nursed {A_him} through it and will say only that the tea helped.",
     "{A} wstał{A?|a} i chodzi po dziedzińcu, {A?chudy|chuda} jak szczapa. {B} {B?doglądał|doglądała} {A?go|ją} do końca i powie tylko, że herbata pomogła."),
]
POOLS["hunger"] = [
    ("*", "b", "A kid asks {A} why the soup is clear today. {A} says the carrots are shy. The kid looks at the pot, then at {A}, and does not ask again.",
     "Dziecko pyta, czemu zupa jest dziś przezroczysta. {A} odpowiada, że marchewki są nieśmiałe. Dziecko patrzy na garnek i nie pyta więcej."),
    ("*", "b", "Hungry again. {A} cuts a slice of bread so thin you could read the roster through it, and hands it to {B} as if it were a banquet.",
     "Znowu głód. {A} kroi kromkę tak cienką, że przez nią można czytać listę, i podaje dalej jak ucztę; bierze ją {B}."),
    ("W", "b", "Mess hall is quiet, the loud kind of quiet. {A} puts a cracker on every tray, a third of one, and tells the kitchen it was always meant to be this way.",
     "W stołówce cisza, ta głośna. {A} kładzie na każdej tacy krakersa, a właściwie jego trzecią część, i mówi kuchni, że tak miało być od zawsze."),
    ("S", "b", "The fasting has been called early. {A} says it is a gift; {B} says it is a hunger with a nice name. They both go to the evening prayer anyway.",
     "Post ogłoszono wcześniej. {A} mówi, że to dar; {B} mówi, że to głód z ładną nazwą. Oboje i tak idą na wieczorną modlitwę."),
]

# ----------------------------------------------------------------------------------------------------------------- the living
POOLS["newcomer"] = [
    ("W", "g", "A new face at the gate: {A}. Hungry, quiet, carrying one boot in each hand. {B} gets {A_him} a bunk, a tin and a name tag that will be right by Friday.",
     "Nowa twarz przy bramie: {A}. {A?Głodny|Głodna}, {A?cichy|cicha}, z jednym butem w każdej ręce. {B} załatwia {A?mu|jej} pryczę, puszkę i identyfikator, który do piątku będzie właściwy."),
    ("S", "g", "{A} came out of the dark with the tide. The Sisters ask no questions on the first night. {B} gives {A_him} a blanket and the place by the fire.",
     "{A} {A?wyszedł|wyszła} z ciemności razem z przypływem. Siostry nie zadają pytań pierwszej nocy. {B} daje {A?mu|jej} koc i miejsce przy ogniu."),
    ("*", "g", "{A} joined us today. A stranger at noon, and by supper {A} had already fixed the door that has been squeaking for a month.",
     "{A} dołączył{A?|a} do nas dziś. W południe {A?obcy|obca}, a przy kolacji już naprawił{A?|a} drzwi, które skrzypiały od miesiąca."),
]
POOLS["kids"] = [
    ("*", "g", "The kids built a fort from empty ration boxes and named it {map}. {A} was made its general, on the condition that every order comes with a salute.",
     "Dzieci zbudowały fort z pustych skrzynek po racjach i nazwały go {map}. {A} został{A?|a} jego generałem pod warunkiem, że za każdym razem salutuje."),
    ("W", "*", "The little ones play WLF against Scars in the yard now. Nobody wants to be the Scars. {A} stands in the middle of the game and gets shot, happily.",
     "Maluchy bawią się teraz w WLF przeciw Bliznom. Nikt nie chce być Bliznami. {A} staje na środku zabawy i dostaje kulkę, z zadowoleniem."),
    ("S", "*", "The children teach each other the signs for fear and for home. {A} watches from the doorway: the two signs are very close to each other.",
     "Dzieci uczą się nawzajem znaków strachu i domu. {A} patrzy z progu: te dwa znaki są bardzo blisko siebie."),
    ("*", "b", "A boy woke screaming for his father. {A} sat with him till morning and told him the only story {A} remembers all the way through, about a dog that waited.",
     "Chłopiec obudził się z krzykiem, wołając ojca. {A} siedział{A?|a} przy nim do rana i opowiadał{A?|a} jedyną historię, którą zna do końca, o psie, który czekał."),
]
POOLS["quarrel"] = [
    ("*", "b", "{A} and {B} had words over the last can of peaches. It ended with {A} giving {B} the can and {B} giving it back. The can is still sealed.",
     "{A} i {B} pokłócili się o ostatnią puszkę brzoskwiń. Skończyło się tym, że puszka krąży między nimi tam i z powrotem. Wciąż jest zamknięta."),
    ("W", "b", "{A} and {B} stopped speaking after the watch roster. By evening they are standing back to back on the wall, which is the closest thing to talking.",
     "{A} i {B} przestali ze sobą rozmawiać po grafiku wart. Wieczorem stoją plecami do siebie na murze, co jest najbliższe rozmowie."),
    ("S", "b", "{A} said something about the elders that {B} will not forgive. The Sisters ask them to share a bowl and a silence. They do, after a while.",
     "{A} powiedział{A?|a} coś o starszych, czego {B} nie wybaczy. Siostry proszą, by podzielili się miską i ciszą. Po jakimś czasie to robią."),
    ("*", "g", "{A} and {B} made up. Nobody saw it. There is just a cup on {A_his} bunk that was not there this morning, and a very straight face on {B}.",
     "{A} i {B} się pogodzili. Nikt tego nie widział. Jest tylko kubek, którego rano na pryczy nie było, i {B} z bardzo poważną miną."),
]
POOLS["quiet"] = [
    ("*", "n", "Nothing happened today, and nobody is brave enough to say so aloud. {A} just repaired a sock by the stove, and smiled.",
     "Nic się dziś nie stało i nikt nie ma odwagi powiedzieć tego głośno. {A} po prostu cerował{A?|a} skarpetę przy piecu i się uśmiechał{A?|a}."),
    ("W", "n", "Lights out at ten. For once the generator holds, and the barracks hums like a house. {A} says goodnight to every bunk by name.",
     "Gaszenie świateł o dziesiątej. Raz agregat wytrzymuje, a koszary szumią jak dom. {A} mówi dobranoc każdej pryczy po imieniu."),
    ("S", "n", "The tide is out and the nets are mending. {A} sings the one about the fisherman's wife, and half the long house hums the second voice.",
     "Odpływ i sieci się naprawiają. {A} śpiewa tę o żonie rybaka, a pół długiego domu mruczy drugi głos."),
]

# ----------------------------------------------------------------------------------------------------------------- how a person reacts (by temperament), appended to a headline
POOLS["react_g"] = [
    ("*", "calm", "{A} nods slowly, the way {A} always does when things are fine and the luck must not be spooked.",
     "{A} kiwa powoli głową, tak jak robi, gdy jest dobrze i nie chce zapeszać."),
    ("*", "hot", "{A} slaps the table, once, hard, and is grinning like an idiot.", "{A} uderza dłonią w stół, raz, mocno, i szczerzy się jak {A?głupi|głupia}."),
    ("*", "anxious", "{A} keeps looking at the door as if the good news might be a trick.", "{A} ciągle patrzy na drzwi, jakby dobra wiadomość mogła być podstępem."),
    ("*", "dry", "{A} says it is suspicious to be this lucky, and takes a second helping anyway.", "{A} mówi, że takie szczęście jest podejrzane, i mimo to bierze dokładkę."),
    ("*", "tender", "{A} quietly puts the best piece on {B}'s plate and pretends to look elsewhere.", "{A} po cichu przesuwa najlepszy kawałek na drugi talerz i udaje, że patrzy gdzie indziej. Ten talerz należy do {B}."),
    ("*", "stubborn", "{A} refuses to be cheered up until the numbers have held three days in a row.", "{A} nie da się rozweselić, dopóki liczby nie utrzymają się trzy dni z rzędu."),
]
POOLS["react_b"] = [
    ("*", "calm", "{A} says nothing and does the next useful thing, then the one after that.", "{A} nic nie mówi i robi następną pożyteczną rzecz, a potem kolejną."),
    ("*", "hot", "{A} kicks a bucket across the yard, then walks after it and picks it up, and says sorry to the bucket.",
     "{A} kopie wiadro przez całe podwórze, potem idzie za nim, podnosi je i przeprasza wiadro."),
    ("*", "anxious", "{A} cannot sit still; {A} rechecks every lock twice and only then lets go of a breath.",
     "{A} nie może usiedzieć; sprawdza każdy zamek dwa razy i dopiero wtedy pozwala sobie odetchnąć."),
    ("*", "dry", "{A} says at least the weather is consistent. It is raining. It is always raining.", "{A} mówi, że przynajmniej pogoda jest stała. Pada. Zawsze pada."),
    ("*", "tender", "{A} goes from bunk to bunk with a little something for each of them, a button, a rhyme, a hand on the shoulder.",
     "{A} chodzi od pryczy do pryczy z drobiazgiem dla każdego, guzikiem, rymowanką, ręką na ramieniu."),
    ("*", "stubborn", "{A} says we have been through worse, and recites the dates, as if to dare them to come back.",
     "{A} mówi, że przeszliśmy gorsze rzeczy, i wymienia daty, jakby wyzywał{A?|a} je, żeby wróciły."),
]

# ----------------------------------------------------------------------------------------------------------------- the small personal habit of A (a closing touch)
POOLS["habit"] = [
    ("*", "*", "{A} winds a wristwatch that has been dead since spring, every dawn, and checks it against the sun.",
     "{A} nakręca zegarek, który nie chodzi od wiosny, co świt, i sprawdza go ze słońcem."),
    ("*", "*", "{A} hums the same three bars over and over; by now the whole camp knows the fourth.",
     "{A} nuci w kółko te same trzy takty; cały obóz zna już czwarty."),
    ("*", "*", "{A} writes every day on the inside of {A_his} cap, in tiny letters. Nobody has ever been allowed to read it.",
     "{A} codziennie pisze drobnymi literami wewnątrz swojej czapki. Nikomu nigdy nie wolno było tego przeczytać."),
    ("*", "*", "{A} carries a tin mug on a string, and drinks from no other.", "{A} nosi blaszany kubek na sznurku i z żadnego innego nie pije."),
    ("*", "*", "{A} leaves the last spoonful for the dog who isn't there anymore.", "{A} zostawia ostatnią łyżkę dla psa, którego już nie ma."),
    ("*", "*", "{A} keeps a stub of pencil behind {A_his} ear and draws a small flower next to every name on the roster that comes back.",
     "{A} trzyma za uchem ogryzek ołówka i rysuje mały kwiatek przy każdym imieniu na liście, kto wraca."),
    ("*", "*", "{A} still makes the bed in the morning, tight, like someone might inspect it.", "{A} nadal rano ściele łóżko, ciasno, jakby ktoś miał je sprawdzić."),
    ("*", "*", "{A} sleeps with {A_his} boots under the pillow, laces tied.", "{A} śpi z butami pod poduszką, sznurowadła związane."),
    ("*", "*", "{A} talks to the radio even when it is off. Mostly weather, and sometimes names.", "{A} rozmawia z radiem, nawet wyłączonym. Głównie o pogodzie, czasem o imionach."),
    ("*", "*", "{A} peels an apple that is not there, in one long motion, a habit from a kitchen that no longer exists.",
     "{A} obiera jabłko, którego nie ma, jednym długim ruchem, nawyk z kuchni, której już nie ma."),
    ("W", "*", "{A} salutes the flag on the old pole each morning, with a hand that has seen too much to be ironic about it.",
     "{A} co rano salutuje fladze na starym maszcie, dłonią, która widziała za dużo, by być w tym ironiczna."),
    ("S", "*", "{A} ties a new thread to the wrist cord for every day survived. By now the cord reaches the elbow.",
     "{A} wiąże nową nitkę na sznurku na nadgarstku za każdy przeżyty dzień. Teraz sznurek sięga łokcia."),
]

# ----------------------------------------------------------------------------------------------------------------- the bond of A and B (a closing touch)
POOLS["bond_kin"] = [
    ("*", "g", "{B} puts {B_his} head on {A}'s shoulder. They are family, and neither says it, because it does not need saying.",
     "{B} i {A} siedzą ramię w ramię. Są rodziną i żadne tego nie mówi, bo nie trzeba."),
    ("*", "b", "{B} will not leave {A}'s side tonight. {A} grumbles. {A} does not push {B} away.", "Dziś {B} i {A} chodzą razem krok w krok. {A} marudzi i nie odpycha."),
]
POOLS["bond_mentor"] = [
    ("*", "g", "{B} watches {A} work and says nothing, which is as close as {B} ever gets to saying well done.",
     "{B} patrzy, jak {A} pracuje, i nic nie mówi, co jest najbliższe temu, co {B} kiedykolwiek powiedział{B?|a}: dobra robota."),
    ("*", "b", "{B} tells {A} to eat first. It is an order, but {B}'s voice cracks on it.", "{B} mówi: pierwszy je {A}. To rozkaz, ale głos się na nim łamie."),
]
POOLS["bond_rival"] = [
    ("*", "g", "{B} bets {A} a week of dishes that the good luck will not last. They shake on it, grinning.",
     "{B} i {A} zakładają się o tydzień zmywania, że to szczęście długo nie potrwa. Przybijają piątkę, uśmiechnięci."),
    ("*", "b", "{B} and {A} usually trade insults. Tonight they only trade a cigarette, passed back and forth without a word.",
     "{B} i {A} zwykle wymieniają obelgi. Dziś wymieniają tylko papierosa, podawanego bez słowa w tę i z powrotem."),
]
POOLS["bond_sweet"] = [
    ("*", "g", "{B} ties {A}'s scarf properly, because {A} never does. It is the only touch either of them allows in public.",
     "{B} wiąże szalik jak należy, bo {A} nigdy tego nie robi. To jedyny dotyk, na jaki oboje pozwalają sobie publicznie."),
    ("*", "b", "{B} found {A} on the roof an hour after dark and sat down next to {A_him} without asking. They watched the dark together.",
     "{B} znalazł{B?|a} {A} na dachu godzinę po zmroku i usiadł{B?|a} obok bez pytania. Razem patrzyli w ciemność."),
]

# ----------------------------------------------------------------------------------------------------------------- loot: found after a match, then used in later stories
# {loot} = "a chessboard" / PL {loot_nom} {loot_acc} {loot_ins} (see clan_chronicle.LOOT).  Pools loot_use_<key> are drawn on later days while the item is in the clan.
POOLS["loot_found"] = [
    ("*", "*", "{A} unpacks the sack from {map}: {loot_list}. For a second nobody mentions the count.",
     "{A} rozpakowuje worek z mapy {map} i wyciąga {loot_list}. Przez chwilę nikt nie wspomina o rachunku."),
    ("W", "*", "{A} logs the haul from {map} and sets {loot_list} out on the table. The line marked \"morale\" is the one {A} underlines twice.",
     "{A} spisuje łup z mapy {map} i kładzie na stole {loot_list}. Rubrykę „morale” podkreśla dwa razy."),
    ("S", "*", "{A} lays the gifts from {map} on the long table: {loot_list}. The Sisters bless them one by one.",
     "{A} wykłada na długi stół dary z mapy {map}, czyli {loot_list}. Siostry błogosławią je po kolei."),
    ("*", "*", "{A} turns the sack from {map} out on the floor and finds {loot_list}. The kids are already crawling toward it.",
     "{A} wysypuje worek z mapy {map} na podłogę i znajduje {loot_list}. Dzieci już się do tego czołgają."),
]
POOLS["loot_use_chess"] = [
    ("*", "*", "The kids play chess on the chessboard from {map}, with bottle caps for pawns and a spent shell for the king. {A} was made referee and takes it very seriously.",
     "Dzieci grają w szachy na szachownicy z mapy {map}, z kapslami zamiast pionków i łuską zamiast króla. {A} został{A?|a} sędzią i traktuje to bardzo poważnie."),
    ("*", "*", "{A} lost to a seven-year-old at chess, twice, and demanded a rematch. The whole room is watching the board like a boxing ring.",
     "{A} przegrał{A?|a} z siedmiolatkiem w szachy, dwa razy, i zażądał{A?|a} rewanżu. Cała izba patrzy na planszę jak na ring bokserski."),
]
POOLS["loot_use_guitar"] = [
    ("*", "*", "{A} restrung the old guitar with the string from {map}. It plays out of tune but it plays, and the room goes quiet to listen.",
     "{A} {A?naciągnął|naciągnęła} starą gitarę struną z mapy {map}. Gra fałszywie, ale gra, i cała izba cichnie, żeby słuchać."),
    ("*", "g", "Somebody found the chords to a song everyone knows. {A} plays it twice, softly, and no one admits they are singing.",
     "Ktoś odnalazł chwyty do piosenki, którą wszyscy znają. {A} gra ją dwa razy, cicho, i nikt nie przyznaje się, że śpiewa."),
]
POOLS["loot_use_comic"] = [
    ("*", "*", "The comic from {map} has been read aloud so many times the kids can do the voices. {A} does the villain, and has been asked to do it again.",
     "Komiks z mapy {map} został przeczytany na głos tyle razy, że dzieci robią głosy. {A} czyta złoczyńcę i już poproszono o bis."),
    ("*", "*", "Two pages of the comic went missing. A trial is held in the yard. The accused, a boy of nine, has chocolate on his face and no chocolate exists.",
     "Z komiksu zniknęły dwie strony. Na podwórzu odbywa się proces. Oskarżony, dziewięciolatek, ma czekoladę na twarzy, a czekolady nie ma."),
]
POOLS["loot_use_teddy"] = [
    ("*", "*", "The teddy bear from {map} is missing an eye and has been given a rank. {A} salutes it every morning, and the smallest kid salutes {A}.",
     "Pluszowy miś z mapy {map} nie ma jednego oka i dostał stopień. {A} salutuje mu co rano, a najmniejsze dziecko salutuje obu naraz."),
    ("*", "b", "A girl slept through the night with the bear from {map} for the first time since the shelter. {A} did not tell anyone, in case it jinxed it.",
     "Dziewczynka po raz pierwszy od schronu przespała całą noc z misiem z mapy {map}. {A} nikomu nie powiedział{A?|a}, żeby nie zapeszyć."),
]
POOLS["loot_use_seeds"] = [
    ("*", "*", "{A} planted the seeds from {map} in a bucket by the window, and guards the bucket from the whole clan. Nothing has come up yet.",
     "{A} zasadził{A?|a} nasiona z mapy {map} w wiadrze przy oknie i broni wiadra przed całym klanem. Na razie nic nie wzeszło."),
    ("*", "g", "Something green is showing in the seed bucket. {A} says it could be a weed. Everybody has come to look at it anyway.",
     "W wiadrze z nasionami coś zielonego wyszło na wierzch. {A} mówi, że to może być chwast. Wszyscy i tak przyszli popatrzeć."),
]
POOLS["loot_use_cards"] = [
    ("*", "*", "The deck of cards from {map} is two short, so the clan plays with a folded note for the queen of hearts. {A} cheats and everyone knows it.",
     "W talii kart z mapy {map} brakuje dwóch, więc klan gra ze złożoną kartką jako damą kier. {A} oszukuje i wszyscy o tym wiedzą."),
    ("*", "b", "Cards by candlelight, for matches. The stakes are tomorrow's chores. {A} loses with grace, then asks for a rematch with disgrace.",
     "Karty przy świecy, o zapałki. Stawką są jutrzejsze obowiązki. {A} przegrywa z gracją, po czym prosi o rewanż bez niej."),
]
POOLS["loot_use_harmonica"] = [
    ("*", "*", "{A} found out how to play the harmonica from {map}. It is mostly a wheeze, but the wheeze has a tune hiding in it.",
     "{A} odkrył{A?|a}, jak grać na harmonijce z mapy {map}. To głównie sapanie, ale w tym sapaniu kryje się melodia."),
    ("*", "b", "At dusk someone plays the harmonica from {map} on the wall, slow and low. Nobody on the watch looks down. Nobody wants to break it.",
     "O zmierzchu ktoś gra na murze na harmonijce z mapy {map}, wolno i nisko. Nikt z warty nie patrzy w dół. Nikt nie chce tego przerwać."),
]

# practical loot: {item} = the held quantity ("15 .38 rounds"), {thing} = one unit ("the can of pineapple")
POOLS["use_food"] = [
    ("*", "*", "{A} split {thing} between the twins, down to the syrup, and ate none of it. {B} noticed, and put the spoon in {A_his} hand.",
     "{A} podzielił{A?|a} {thing} między bliźnięta, do ostatniej kropli syropu, i nic nie zjadł{A?|a}. {B} to zauważył{B?|a} i włożył{B?|a} łyżkę do ręki {A?mu|jej}."),
    ("*", "g", "{A} cooks {item} for supper and serves it with a ceremony nobody asked for, and it is the best-attended meal in a month.",
     "{A} przygotowuje na kolację {item}. Podaje to z ceremonią, o którą nikt nie prosił, i to najlepiej obecny posiłek od miesiąca."),
    ("W", "b", "{A} locks {item} in the footlocker and carries the key on a string. Rations are rations, {A} says, and the mess hall hates {A_him} for it a little.",
     "{A} zamyka {item} w kufrze i nosi klucz na sznurku. Racje to racje, mówi {A}, a stołówka trochę za to {A?go|ją} nienawidzi."),
    ("S", "*", "Before {thing} is opened {A} says the grace, the long one, and the children wait with spoons raised like small spears.",
     "Zanim ktoś otworzy {thing}, {A} mówi modlitwę dziękczynną, tę długą, a dzieci czekają z łyżkami uniesionymi jak małe włócznie."),
]
POOLS["use_med"] = [
    ("*", "*", "{A} counts {item} twice and writes the number on the inside of the cupboard door, where only the sick will see it.",
     "{A} liczy {item} dwa razy i zapisuje liczbę po wewnętrznej stronie drzwiczek szafki, gdzie zobaczą ją tylko chorzy."),
    ("*", "b", "{B} is feverish again. {A} opens {thing} without a word, and the room listens to the seal break as if it were a door.",
     "{B} znowu ma gorączkę. {A} otwiera {thing} bez słowa, a izba słucha, jak pęka plomba, jakby to były drzwi."),
    ("W", "*", "The medic's bag has {item} in it now. {A} checks it every hour, and pretends it is the only thing {A} checks.",
     "{A} pakuje do torby medyka {item}. Sprawdza ją co godzinę i udaje, że tylko to sprawdza."),
    ("S", "*", "{A} blesses {item} before it goes in the healing house. {B} says medicine does not care. {A} says the hands that use it might.",
     "{A} błogosławi {item}, zanim trafi do domu uzdrowień. {B} mówi, że lekarstwu to obojętne. {A} odpowiada, że rękom, które je podadzą, może nie."),
]
POOLS["use_ammo"] = [
    ("*", "*", "{A} counted {item} twice before the raid, then asked {B} to count them a third time, because {A} did not trust {A_his} own fingers.",
     "{A} przeliczył{A?|a} {item} dwa razy przed wypadem, po czym poprosił{A?|a} {B}, żeby policzył{B?|a} po raz trzeci, bo nie ufał{A?|a} własnym palcom."),
    ("W", "*", "By lamplight {A} thumbs {item} into the magazines, pressing each round down and saying its number, like a small prayer.",
     "Przy lampie {A} wciska {item} do magazynków, dociskając każdy nabój kciukiem i mówiąc jego numer, jak małą modlitwę."),
    ("S", "*", "{A} hands out {item} for the hunt, one at a time, and each hunter must say what they will not shoot at.",
     "{A} wydaje {item} na polowanie, po jednym, a każdy łowca musi powiedzieć, do czego nie wystrzeli."),
]
POOLS["use_tool"] = [
    ("*", "*", "{A} has found a use for {thing} before the sun is up, and by noon three other people have found different ones. {B} just wants it back.",
     "{A} znalazł{A?|a} pomysł na {thing} przed wschodem słońca, a do południa trzy inne osoby znalazły własne. {B} chce tylko, żeby to wróciło."),
    ("*", "g", "With {item} in the tool chest {A} actually finishes the gate latch. It clicks. The whole yard stops and listens to it click again.",
     "Mając {item} w skrzyni z narzędziami, {A} wreszcie kończy zamek w bramie. Klika. Całe podwórze zatrzymuje się i słucha, jak klika jeszcze raz."),
    ("*", "b", "{A} is rationing {item}, and the clan has noticed. There is a list on the wall, and the first name on it is {A}'s own.",
     "{A} racjonuje {item}, a klan to zauważył. Na ścianie wisi lista, a pierwsze nazwisko na niej to {A}."),
]

POOLS["react_g"] += [
    ("*", "calm", "{A} just sits for a while with both hands around a cup and lets the day be good.", "{A} po prostu siedzi chwilę z obiema dłońmi wokół kubka i pozwala dniu być dobrym."),
    ("*", "hot", "{A} is already planning the next one, loudly, with a spoon for a pointer.", "{A} już planuje następny raz, głośno, z łyżką zamiast wskaźnika."),
    ("*", "anxious", "{A} says it out loud so the luck can hear: thank you, please stay.", "{A} mówi to na głos, żeby szczęście usłyszało: dziękuję, zostań."),
    ("*", "dry", "{A} remarks that this is the part of the story where something goes wrong, and eats anyway.", "{A} zauważa, że to ten fragment historii, w którym coś idzie źle, i mimo to je."),
    ("*", "tender", "{A} hums while washing the cups, and has no idea it carries all the way to the gate.", "{A} nuci, myjąc kubki, i nie wie, że słychać to aż pod bramą."),
    ("*", "stubborn", "{A} says it was never luck, it was a plan, and will not be argued with about it.", "{A} mówi, że to nigdy nie było szczęście, tylko plan, i nie da się z tym dyskutować."),
]
POOLS["react_b"] += [
    ("*", "calm", "{A} wipes the table twice, slowly, because it is something that can be finished.", "{A} wyciera stół dwa razy, powoli, bo to coś, co da się skończyć."),
    ("*", "hot", "{A} says a few things about the world that cannot be repeated in front of the kids.", "{A} mówi kilka rzeczy o świecie, których nie wolno powtarzać przy dzieciach."),
    ("*", "anxious", "{A} sleeps sitting up tonight, back to the wall, one hand on the lantern.", "{A} śpi dziś na siedząco, plecami do ściany, z jedną ręką na latarni."),
    ("*", "dry", "{A} says the good news is that it can hardly get worse, then looks at the sky as if daring it.", "{A} mówi, że dobra wiadomość jest taka, że gorzej już chyba nie będzie, i patrzy w niebo, jakby je wyzywał{A?|a}."),
    ("*", "tender", "{A} sits with whoever is awake, saying nothing, which is somehow the right thing.", "{A} siedzi z każdym, kto nie śpi, nic nie mówiąc, i to jakoś jest właściwe."),
    ("*", "stubborn", "{A} gets up at dawn and does the same work as yesterday, exactly, out of principle.", "{A} wstaje o świcie i robi tę samą robotę co wczoraj, co do joty, z zasady."),
]

POOLS["ration"] += [
    ("*", "g", "The ration board is changed back to the old numbers. {A} rubs out the small, sad ones with the heel of a hand and writes the fat ones twice.",
     "Tablica z racjami wraca do dawnych liczb. {A} wyciera brzegiem dłoni te małe, smutne i wpisuje te tłuste po dwa razy."),
    ("W", "g", "{A} opens the locked footlocker and puts a tin on the mess table for no reason at all. The mess pretends not to notice, then notices.",
     "{A} otwiera zamknięty kufer i stawia puszkę na stole w stołówce bez żadnego powodu. Stołówka udaje, że nie widzi, a potem widzi."),
    ("S", "g", "The Sisters set an extra bowl at the long table, for whoever is hungry and has not yet said so. {A} fills it.",
     "Siostry stawiają na długim stole dodatkową miskę, dla każdego, kto jest głodny i jeszcze tego nie powiedział. {A} ją napełnia."),
    ("*", "b", "{A} weighs the bread on a homemade scale in front of everyone. The pan sinks a little less than yesterday, and nobody says what that means.",
     "{A} waży chleb na domowej wadze na oczach wszystkich. Szalka opada trochę mniej niż wczoraj i nikt nie mówi, co to znaczy."),
]

POOLS["habit"] += [
    ("*", "*", "{A} keeps bottle caps in a sock and counts them every night; the number is a secret.", "{A} trzyma kapsle w skarpecie i co noc je liczy; liczba jest tajemnicą."),
    ("*", "*", "{A} draws the same little house on every wall that will take chalk: a door, a window, smoke from the chimney.",
     "{A} rysuje kredą na każdej ścianie ten sam mały domek: drzwi, okno, dym z komina."),
    ("*", "*", "{A} will not sleep without a flashlight that has no batteries, and nobody has the heart to say so.",
     "{A} nie zaśnie bez latarki bez baterii i nikt nie ma serca tego powiedzieć."),
    ("*", "*", "{A} whispers to a stone in {A_his} pocket, and the stone has opinions.", "{A} szepcze do kamienia w kieszeni, a kamień ma swoje zdanie."),
    ("*", "*", "{A} tells the weather by a bad knee and has not been wrong in a year.", "{A} przepowiada pogodę po bolącym kolanie i od roku się nie pomyliło."),
    ("*", "*", "{A} recites the names of the old streets like a rosary, in order, and corrects anyone who skips one.",
     "{A} odmawia nazwy dawnych ulic jak różaniec, po kolei, i poprawia każdego, kto jakąś pominie."),
    ("*", "*", "{A} owns reading glasses with one lens and reads every label twice, just to be sure.", "{A} ma okulary do czytania z jednym szkłem i każdą etykietę czyta dwa razy, na wszelki wypadek."),
    ("*", "*", "{A} whittles a little something from every scrap of wood and gives it away before it is dry.", "{A} struga coś małego z każdego kawałka drewna i oddaje to, zanim wyschnie."),
    ("*", "*", "{A} saves the foil from every ration, for reasons {A} will not share.", "{A} chowa folię z każdej racji z powodów, których nie zdradza."),
    ("*", "*", "{A} counts the stairs aloud, thirty-one, even in the dark, even when there are only twenty-nine.", "{A} liczy schody na głos, trzydzieści jeden, nawet po ciemku, nawet gdy jest ich tylko dwadzieścia dziewięć."),
    ("*", "*", "{A} always sits facing the door, and goes very quiet when someone else has the chair.", "{A} zawsze siada twarzą do drzwi i cichnie, gdy to krzesło zajmie ktoś inny."),
    ("*", "*", "{A} presses flowers between the pages of the camp ledger, so the numbers bloom.", "{A} suszy kwiaty między kartami obozowej księgi, żeby liczby kwitły."),
    ("*", "*", "{A} taps twice on every doorframe going in, for luck, and once going out, for thanks.", "{A} stuka dwa razy we framugę przy wejściu, na szczęście, i raz przy wyjściu, w podziękowaniu."),
    ("*", "*", "{A} reads the labels of empty tins aloud, like a menu.", "{A} czyta na głos etykiety pustych puszek, jak menu."),
    ("W", "*", "{A} polishes the same pair of boots every Sunday, though nobody agrees which day Sunday is.", "{A} pastuje te same buty w każdą niedzielę, choć nikt nie wie, który dzień jest niedzielą."),
    ("S", "*", "{A} knots a bit of thread into a stranger's sleeve, \"for the road\", and has never been refused.", "{A} wiąże kawałek nitki w rękaw obcego, „na drogę”, i nigdy mu nie odmówiono."),
    ("*", "*", "{A} sings to the generator and swears it runs better for it.", "{A} śpiewa agregatowi i przysięga, że dzięki temu lepiej chodzi."),
]

POOLS["match_kills"] = [
    ("W", "*", "{kills} of {enemies} down on {map} today. {A} marks each one on the wall in pencil, and the pencil is nearly gone.",
     "Dziś na mapie {map} po ich stronie {kills}. {A} zaznacza każdego ołówkiem na ścianie i ołówek prawie się skończył."),
    ("S", "*", "On {map} the hunters brought down {kills} of {enemies}. {A} says the count aloud, and the long house says nothing back.",
     "Na mapie {map} łowcy powalili {kills} z {enemy_gen}. {A} mówi liczbę na głos, a długi dom nie odpowiada."),
    ("*", "*", "A short report from {map}: {kills} of theirs put down. {A} nods and asks only whether everyone came home to eat.",
     "Krótki raport z mapy {map}: {kills} po ich stronie. {A} kiwa głową i pyta tylko, czy wszyscy wrócili na kolację."),
    ("*", "*", "{map} was quiet, which is the worst kind of day. {kills} of theirs, and a sky full of weather. {A} cleans a rifle that is already clean.",
     "Mapa {map} była cicha, a to najgorszy rodzaj dnia. {kills} ich i niebo pełne pogody. {A} czyści karabin, który jest już czysty."),
    ("*", "*", "{kills} down on {map}. Nobody makes a speech. {A} puts the kettle on and the whole camp drifts toward the sound.",
     "{kills} powalonych na mapie {map}. Nikt nie wygłasza przemówienia. {A} stawia czajnik i cały obóz ciągnie za dźwiękiem."),
]

POOLS["habit"] += [
    ("*", "*", '{A} patches the same jacket every week, with a different colour of thread each time, and the jacket is mostly patch now.', '{A} łata tę samą kurtkę co tydzień nitką innego koloru i kurtka jest już głównie łatą.'),
    ("*", "*", '{A} hoards pencil stubs in a tobacco tin and lends them out against a promise to return them.', '{A} zbiera ogryzki ołówków w puszce po tytoniu i pożycza je za obietnicę zwrotu.'),
    ("*", "*", '{A} washes the same cup three times before drinking, then drinks before it can dry.', '{A} myje ten sam kubek trzy razy przed piciem, po czym pije, zanim zdąży wyschnąć.'),
    ("*", "*", '{A} walks the wall at dusk, one hand trailing along the stones, as if checking they are all still there.', '{A} obchodzi mur o zmierzchu, jedną dłonią sunąc po kamieniach, jakby sprawdzał{A?|a}, czy wszystkie są na miejscu.'),
    ("*", "*", '{A} knows every can of food in camp by its dent and gives them names.', '{A} zna każdą puszkę w obozie po wgnieceniu i nadaje im imiona.'),
    ("*", "*", '{A} falls asleep over a book with the cover missing, and wakes up angry at the ending.', '{A} zasypia nad książką bez okładki i budzi się {A?zły|zła} na zakończenie.'),
    ("*", "*", '{A} whistles one note when passing the infirmary door, always the same, and nobody asks why.', '{A} gwiżdże jeden dźwięk, mijając drzwi izby chorych, zawsze ten sam, i nikt nie pyta dlaczego.'),
    ("*", "*", '{A} keeps a jar of sand from the beach, and turns it over when the news is bad.', '{A} trzyma słoik piasku z plaży i obraca go, gdy wieści są złe.'),
    ("*", "*", "{A} mends other people's laces before they notice they are fraying.", '{A} naprawia cudze sznurowadła, zanim ktoś zauważy, że się strzępią.'),
    ("*", "*", '{A} writes a letter every Friday to someone far away, and burns it on Saturday, and writes again.', '{A} pisze w każdy piątek list do kogoś daleko, pali go w sobotę i pisze od nowa.'),
    ("*", "*", '{A} chews a matchstick all day and never lights it.', '{A} cały dzień żuje zapałkę i nigdy jej nie zapala.'),
    ("*", "*", '{A} sets one extra place at the table, and nobody has ever sat in it, and nobody has ever taken it away.', '{A} stawia jedno dodatkowe miejsce przy stole; nikt nigdy tam nie usiadł i nikt go nie sprzątnął.'),
]
