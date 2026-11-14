"""A-Life text pools, part E: more phrasings for the storylines that run most often (the repeat window is 4 weeks, so a pool has to be wide), plus the role
and trait lines of the ticker.  These rows are APPENDED to the pools of the same name in parts A-D (clan_alife.py merges them).  Row format: see clan_alife_text_a.py."""

POOLS = {}

POOLS["arrive"] = [
    ("*", "*", "{A} {job} once, and it shows: {A_he} is already fixing things nobody asked {A_him} to fix.",
     "{A} kiedyś {job}, i to widać: już naprawia rzeczy, o które nikt {A?go|ją} nie prosił."),
    ("*", "g", "{A} is handed over to {B} for the first week. By evening they are on first-name terms and sharing a cup.",
     "{A} trafia na pierwszy tydzień pod opiekę, którą sprawuje {B}. Do wieczora są na ty i piją z jednego kubka."),
    ("*", "b", "{A} counts the exits before sitting down. {B} sees it, and takes the seat nearest the door, so {A} does not have to.",
     "{A} liczy wyjścia, zanim usiądzie. {B} to widzi i zajmuje miejsce najbliżej drzwi, żeby {A} nie musiał{A?|a}."),
    ("*", "n", "{A} has a blanket, a knife and a way of listening. {B} says that is enough to start with.",
     "{A} ma koc, nóż i sposób słuchania. {B} mówi, że to wystarczy na początek."),
    ("W", "*", "{A} asks for the work nobody wants. {B} gives {A_him} the latrine, and {A} thanks {B_him}.",
     "{A} prosi o robotę, której nikt nie chce. {B} daje {A?mu|jej} latrynę, a {A} dziękuje."),
    ("S", "*", "{A} asks for the work nobody wants. {B} gives {A_him} the nets, and {A} thanks {B_him}.",
     "{A} prosi o robotę, której nikt nie chce. {B} daje {A?mu|jej} sieci, a {A} dziękuje."),
]
POOLS["wx_rain"] = [
    ("*", "*", "Water is running off every roof, and the buckets fill faster than they can be emptied.",
     "Z każdego dachu płynie woda, a wiadra napełniają się szybciej, niż da się je opróżniać."),
    ("*", "b", "The rain has put out half the cook fires and all of the good moods.", "Deszcz zgasił połowę ognisk i wszystkie dobre nastroje."),
    ("W", "*", "Rain on the sandbags; the yard is one long puddle.", "Deszcz na workach z piaskiem; podwórze to jedna długa kałuża."),
    ("S", "*", "Rain on the thatch, rain on the water, and rain on the prayers.", "Deszcz na strzesze, deszcz na wodzie i deszcz na modlitwach."),
]
POOLS["wx_fog"] = [
    ("*", "*", "The fog is so thick the watch calls out the hours just to hear a voice.", "Mgła jest tak gęsta, że wartownicy wołają godziny tylko po to, by usłyszeć czyjś głos."),
    ("*", "*", "Wet gray nothing outside the fence. Even the dogs are quiet.", "Mokra szara pustka za ogrodzeniem. Nawet psy są cicho."),
]
POOLS["wx_cold"] = [
    ("*", "*", "Frost on the inside of the windows, and everyone sleeps in pairs for warmth.", "Szron po wewnętrznej stronie okien i wszyscy śpią parami, żeby było cieplej."),
    ("*", "*", "The cold makes the water barrels ring like bells when anyone knocks them.", "Mróz sprawia, że beczki z wodą dźwięczą jak dzwony, gdy ktoś w nie stuknie."),
]
POOLS["wx_clear"] = [
    ("*", "g", "A clean, bright morning; the smoke from the cook fires goes straight up.", "Czysty, jasny poranek; dym z ognisk idzie prosto w górę."),
    ("*", "*", "Long shadows, cold light, and for an hour the whole world looks undamaged.", "Długie cienie, zimne światło i przez godzinę cały świat wygląda na nietknięty."),
]
POOLS["wx_wind"] = [
    ("*", "*", "Wind rattles every shutter, and the camp talks in raised voices all day.", "Wiatr trzęsie każdą okiennicą i obóz przez cały dzień rozmawia podniesionymi głosami."),
]
POOLS["wx_smoke"] = [
    ("*", "*", "Ash on every windowsill this morning; nobody can say whose fire it was.", "Dziś rano na każdym parapecie popiół; nikt nie umie powiedzieć, czyj to był ogień."),
]
POOLS["proj_done"] = [
    ("*", "*", "{A} and {B} finish the work on {proj} and stand looking at it as if it might say something.",
     "{A} i {B} kończą prace nad {proj_ins} i stoją, patrząc na to, jakby miało coś powiedzieć."),
    ("*", "g", "The work on {proj} is done, and the whole camp comes to look. {A} is embarrassed; {B} is proud enough for both.",
     "Prace nad {proj_ins} skończone i cały obóz przychodzi popatrzeć. {A} jest zawstydzon{A?y|a}, a {B} dumn{B?y|a} za oboje."),
    ("*", "n", "The work on {proj} is done. {A} checks it twice, {B} once, and they agree that it will hold.",
     "Prace nad {proj_ins} skończone. {A} sprawdza je dwa razy, {B} raz i uzgadniają, że wytrzyma."),
]
POOLS["proj_prog"] = [
    ("*", "n", "{A} brings a measuring string from somewhere, and for two days nobody builds anything without checking it. The work on {proj} is {prog}.",
     "{A} przynosi skądś miarkę ze sznurka i przez dwa dni nikt nie buduje niczego bez sprawdzenia. Prace nad {proj_ins} {prog}."),
]
POOLS["thr_after"] = [
    ("W", "*", "{A} counts what is left: rounds, bandages, people, in that order. {B} puts the kettle on and does not say what the numbers are.",
     "{A} liczy, co zostało: naboje, bandaże, ludzi, w tej kolejności. {B} stawia czajnik i nie mówi, ile tego jest."),
    ("S", "*", "{A} counts what is left: arrows, bandages, people, in that order. {B} puts the kettle on and does not say what the numbers are.",
     "{A} liczy, co zostało: strzały, bandaże, ludzi, w tej kolejności. {B} stawia czajnik i nie mówi, ile tego jest."),
    ("*", "b", "Everyone sleeps with a weapon within reach tonight. {A} sits up, and {B} sits up with {A_him}, and neither of them says why.",
     "Dziś każdy śpi z bronią w zasięgu ręki. {A} nie kładzie się, {B} czuwa razem z {A?nim|nią} i żadne nie mówi dlaczego."),
    ("*", "*", "{A} patches the hole in the fence with whatever is at hand: a door, a bed frame, a cupboard. {B} holds the other end. It is ugly and it will hold.",
     "{A} łata dziurę w ogrodzeniu czym popadnie: drzwiami, ramą łóżka, szafką. {B} trzyma drugi koniec. Jest brzydkie i da radę."),
]
POOLS["thr_up"] = [
    ("*", "*", "{A} reports that the signs near {dest} have grown. {B} runs to wake the others, then, thinking better of it, walks.",
     "{A} melduje, że znaki w okolicy {dest_gen} się nasiliły. {B} biegnie budzić innych, a potem, pomyślawszy, idzie krokiem."),
    ("*", "n", "The watch near {dest} reports nothing new, which {A} says is exactly the problem.",
     "Warta w okolicy {dest_gen} nie melduje niczego nowego, co {A} uważa za sedno problemu."),
]
POOLS["thr_down"] = [
]
POOLS["exp_ret_good"] = [
    ("*", "*", "{A} and {B} come back from {dest} {nd_after} with {goal}, and with the smell of somewhere else on their coats.",
     "{A} i {B} wracają {dest_from} {nd_after} {goal_with}, a ich płaszcze pachną czymś innym."),
    ("*", "*", "The bags are heavier than they look. {A} and {B} are back from {dest} {nd_after}, and pour {goal} out onto the table.",
     "Torby są cięższe, niż wyglądają. {A} i {B} wracają {dest_from} {nd_after} i wysypują na stół {goal_acc}."),
    ("*", "g", "Somebody has been waiting at the gate since noon. {A} and {B} come in from {dest} {nd_after}, with {goal}, and are hugged by more people than they have ever met.",
     "Ktoś czeka przy bramie od południa. {A} i {B} wchodzą {dest_from} {nd_after} {goal_with} i są ściskan{AB?i|e} przez więcej osób, niż kiedykolwiek pozna{AB?li|ły}."),
    ("*", "n", "Not a bad haul: {goal}, from {dest}. {A} wants a medal for it, and {B} wants it divided before anyone gets sentimental.",
     "Niezły łup: {goal_nom}, {dest_from}. {A} chce za to medal, a {B} chce, żeby to podzielić, zanim ktoś się rozczuli."),
]
POOLS["vigil"] = [
    ("*", "*", "{B} dozes in the chair beside {A}'s bed and wakes every time {A} stirs. {A} has {ill_a}, and has stopped apologising for it.",
     "{B} drzemie na krześle przy łóżku chorego i budzi się za każdym razem, gdy {A} się poruszy. {A} ma {ill_acc} i przestał{A?|a} za to przepraszać."),
    ("*", "*", "{B} reads aloud to {A}, from the one book that has both covers. {A} has {ill_a} and listens with {A_his} eyes shut.",
     "{B} czyta {A?mu|jej} na głos z jedynej książki, która ma obie okładki. {A} ma {ill_acc} i słucha z zamkniętymi oczami."),
    ("*", "b", "{B} hangs a blanket across the window so the draught will not reach {A}. It is the last blanket. {A} has {ill_a}.",
     "{B} wiesza koc w oknie, żeby przeciąg nie sięgał {A?jego|jej} łóżka. To ostatni koc. {A} ma {ill_acc}."),
    ("*", "g", "{A} is better today. Not well, but better, and {B} has stopped looking at the door every time it opens.",
     "{A} czuje się dziś lepiej. Nie dobrze, ale lepiej, a {B} przestał{B?|a} patrzeć na drzwi za każdym razem, gdy się otwierają."),
]
POOLS["vigil_spore"] = [      # the spore-sick (canon: no cure, no recovery): a vigil without hope talk
    ("*", "*", "{B} sits up with {A} again, mask on, at the far side of the lamp. Neither of them says what the cough is.",
     "{B} znów czuwa, w masce, po drugiej stronie lampy; choruje {A}. Żadne z nich nie mówi, czym jest ten kaszel."),
    ("*", "b", "{A} asks {B} to talk about the old days, any of them, and {B} does, for hours, because the alternative is the quiet.",
     "{A} prosi {B}, żeby opowiadał{B?|a} o dawnych czasach, o jakichkolwiek, a {B} opowiada godzinami, bo alternatywą jest cisza."),
    ("*", "*", "{B} brings water and does not bring a promise. {A} notices, and is grateful for the one and for the other.",
     "{B} przynosi wodę i nie przynosi obietnicy. {A} to zauważa i jest wdzięczn{A?y|a} za jedno i za drugie."),
    ("*", "n", "{A} says it is a good night for a story. {B} says tell it, and {A} does, and stops in the middle, and starts again from the beginning.",
     "{A} mówi, że to dobra noc na opowieść. {B} mówi: opowiadaj, i {A} opowiada, urywa w połowie i zaczyna od początku."),
]
POOLS["recovered"] = [
    ("*", "*", "{A} is out in the yard in the thin sun, wrapped to the eyes, and {B} stands guard against anyone who wants to talk.",
     "{A} siedzi na podwórzu w cienkim słońcu, owinięt{A?y|a} po oczy, a {B} pilnuje, żeby nikt nie zaczepiał."),
    ("*", "n", "{A} is eating on {A_his} own again, with {A_his} own hands. {B} has stopped hovering, mostly.",
     "{A} znów je sam{A?|a}, własnymi rękami. {B} przestał{B?|a} krążyć wokół, w większości."),
]
POOLS["rat_deficit"] = [
    ("*", "*", "A thin supper: {sup} against {need}. {A} gives {A_his} bread to a child and pretends it was an accident.",
     "Chuda kolacja: {sup} wobec {need}. {A} oddaje swój chleb dziecku i udaje, że to przypadek."),
    ("*", "b", "{sup} where {need} were needed, and everyone can do that sum. {B} sits very still and {A} sits closer.",
     "{sup}, a potrzeba było {need}, i każdy umie to policzyć. {B} siedzi bardzo nieruchomo, a {A} przysuwa się bliżej."),
]
POOLS["rat_surplus"] = [
    ("*", "*", "Slightly more than enough: {sup} for {need}. {A} puts a handful aside for tomorrow, and {B} quietly adds another.",
     "Odrobinę więcej, niż trzeba: {sup} przy {need}. {A} odkłada garść na jutro, a {B} po cichu dokłada drugą."),
    ("*", "g", "{sup} against {need}: the best day in a while. {A} lets the children stay up, and {B} lets them stay up longer.",
     "{sup} wobec {need}: najlepszy dzień od dawna. {A} pozwala dzieciom posiedzieć dłużej, a {B} jeszcze dłużej."),
    ("W", "*", "{sup} to {need} on the board. The quartermaster smiles, which unsettles the barracks more than the shortages did.",
     "Na tablicy {sup} do {need}. Kwatermistrz się uśmiecha, co niepokoi koszary bardziej niż niedobory."),
]
POOLS["friend"] = [
    ("*", "*", "{A} and {B} found the same old coin in the same old drain, and have not stopped talking about it since.",
     "{A} i {B} znalaz{AB?li|ły} tę samą starą monetę w tym samym starym ścieku i od tamtej pory nie przestają o tym mówić."),
]
POOLS["quarrel"] = [
]
POOLS["reconcile"] = [
    ("*", "*", "{A} and {B} are seen laughing at the same joke. Nobody dares to ask which joke.",
     "{A} i {B} śmieją się z tego samego żartu. Nikt nie ośmiela się pytać, z którego."),
    ("*", "*", "{B} returns the borrowed knife, sharpened. {A} says nothing and returns the borrowed rope, coiled.",
     "{B} oddaje pożyczony nóż, naostrzony. {A} nic nie mówi i oddaje pożyczoną linę, zwiniętą."),
]
POOLS["mentor"] = [
    ("*", "*", "{A} lets {B} try to {skill} alone for the first time, and stands very far away, hands in pockets, with a face of stone.",
     "{B} po raz pierwszy próbuje samodzielnie {skill}, a {A} stoi bardzo daleko, z rękami w kieszeniach i kamienną twarzą."),
    ("*", "n", "{B} writes down what {A} says about how to {skill}. Half of it is wrong, {A} notes, then adds that the other half is the better half.",
     "{B} zapisuje to, co mówi {A} o tym, jak {skill}. Połowa jest błędna, zauważa {A}, po czym dodaje, że druga połowa jest lepsza."),
]
POOLS["amb_any"] = [
    ("*", "*", "{A} and {B} take the washing in before the rain, with a speed nobody knew they had.", "{A} i {B} zbierają pranie przed deszczem z prędkością, o którą nikt ich nie podejrzewał."),
    ("*", "g", "{A} wins the camp's game of draughts, the one with bottle caps and a carved board. {B} demands a rematch and gets it.",
     "{A} wygrywa w obozowe warcaby, te z kapslami i wyrzeźbioną planszą. {B} żąda rewanżu i go dostaje."),
    ("*", "*", "{A} sharpens knives for half the camp and tells each owner how it will be used. {B} asks not to be told.",
     "{A} ostrzy noże połowie obozu i każdemu właścicielowi opowiada, do czego się przyda. {B} prosi, żeby nie mówić."),
    ("*", "g", "{A} finds a pair of boots that fit and is insufferable for the rest of the day.", "{A} znajduje buty, które pasują, i przez resztę dnia jest nie do zniesienia."),
    ("*", "*", "{A} and {B} dig a crate of old tools out from under the north wall and spend the afternoon identifying them.",
     "{A} i {B} odkopują spod północnego muru skrzynię starych narzędzi i spędzają popołudnie na ich rozpoznawaniu."),
    ("*", "g", "{A} teaches the camp a song, and by evening three different versions of it are going round.",
     "{A} uczy obóz piosenki i do wieczora krążą już trzy jej wersje."),
    ("*", "*", "A spoon has gone missing, and {A} is conducting the investigation with the seriousness of a trial.",
     "Zginęła łyżka, a {A} prowadzi śledztwo z powagą procesu."),
    ("*", "*", "{B} reorganises the storeroom according to a system only {B_he} understands. {A} cannot find anything and says so.",
     "{B} porządkuje magazyn według systemu, który rozumie tylko {B?on|ona}. {A} niczego nie może znaleźć i głośno to mówi."),
    ("*", "n", "{A} and {B} carry water in silence, the way you do with someone you have known too long to bother with talk.",
     "{A} i {B} noszą wodę w milczeniu, jak ludzie, którzy znają się zbyt długo, żeby zawracać sobie głowę rozmową."),
    ("*", "b", "A bad night. {A} and {B} take the second watch together, listening to the dark.",
     "Zła noc. {A} i {B} razem biorą drugą wartę, nasłuchując ciemności."),
    ("W", "*", "{A} pins a list of rules to the barracks door. By noon someone has added a rule about the list.",
     "{A} przypina do drzwi koszar listę zasad. Do południa ktoś dopisuje zasadę o liście."),
    ("S", "*", "{A} and {B} carve a new bench for the long house, and argue about whether it should face the fire or the door.",
     "{A} i {B} rzeźbią nową ławę do długiego domu i spierają się, czy ma stać przodem do ognia, czy do drzwi."),
    ("S", "*", "At low tide, {A} and {B} gather mussels along the rocks, and bring back more stories than mussels.",
     "Przy odpływie {A} i {B} zbierają małże wśród skał i przynoszą więcej opowieści niż małży."),
]
POOLS["amb_scavenger"] = [
    ("*", "*", "{A}, the {A_role}, brings back a mirror, a clock without hands and a very good frying pan. {B} gets the pan.",
     "{A}, {A_role}, przynosi lustro, zegar bez wskazówek i bardzo dobrą patelnię. {B} dostaje patelnię."),
    ("*", "*", "{A} keeps a list of everything {A_he} has ever found, and where. The list is longer than the camp's storeroom.",
     "{A} prowadzi listę wszystkiego, co kiedykolwiek znalazł{A?|a}, i gdzie. Lista jest dłuższa niż magazyn obozu."),
]
POOLS["amb_medic"] = [
    ("*", "*", "{A}, the {A_role}, asks everyone to show their hands. Half of the camp discovers it has been washing them wrong.",
     "{A}, {A_role}, prosi wszystkich o pokazanie dłoni. Połowa obozu odkrywa, że myła je źle."),
    ("*", "*", "{A} labels every jar on the medicine shelf in neat capitals, then adds a second label for {B}: DO NOT TOUCH.",
     "{A} podpisuje każdy słoik na półce z lekami równym pismem, a potem dodaje drugą etykietę, specjalnie z myślą o tym, co robi {B}: NIE DOTYKAĆ."),
]
POOLS["amb_cook"] = [
    ("*", "*", "{A}, the {A_role}, makes a stew from five ingredients and tells everyone it has eleven. {B} counts. It has five.",
     "{A}, {A_role}, gotuje gulasz z pięciu składników i mówi wszystkim, że z jedenastu. {B} liczy. Jest pięć."),
    ("*", "n", "{A} burns the bread, and the whole camp pretends it was meant to taste like that. {B} asks for seconds, to be kind.",
     "{A} przypala chleb, a cały obóz udaje, że tak miało smakować. {B} prosi o dokładkę, z uprzejmości."),
]
POOLS["amb_guard"] = [
    ("*", "*", "{A}, the {A_role}, stands the dawn watch and counts the birds. There are eleven. {A_He} writes it down.",
     "{A}, {A_role}, stoi na porannej warcie i liczy ptaki. Jedenaście. {A?On|Ona} to zapisuje."),
    ("*", "n", "'Password!' calls {A} for the third time today, though {B} has slept on the next bunk for a month. Rules are rules.",
     "„Hasło!” — woła {A} po raz trzeci dziś, choć {B} śpi na sąsiedniej pryczy od miesiąca. Regulamin to regulamin."),
]
POOLS["amb_mechanic"] = [
    ("*", "*", "{A}, the {A_role}, makes a hinge from a bike pedal and a spoon. The gate has never swung so well.",
     "{A}, {A_role}, robi zawias z pedału rowerowego i łyżki. Brama nigdy nie otwierała się tak dobrze."),
    ("*", "n", "{A} fixes the same pump for the fourth time this month, and speaks to it with a patience {A_he} shows to no person.",
     "{A} po raz czwarty w tym miesiącu naprawia tę samą pompę i rozmawia z nią z cierpliwością, której nie okazuje żadnemu człowiekowi."),
]
POOLS["amb_scout"] = [
    ("*", "*", "{A}, the {A_role}, climbs the old water tower and comes down with nothing to report, which, {A_he} says, is a sign of good work.",
     "{A}, {A_role}, wchodzi na starą wieżę ciśnień i schodzi bez żadnych wieści, co, jak mówi, świadczy o dobrej robocie."),
    ("*", "n", "{A} marks the safe paths on the map in green, the unsafe ones in red, and the ones {A_he} is unsure of in a color {B} says does not exist.",
     "{A} zaznacza na mapie bezpieczne ścieżki na zielono, niebezpieczne na czerwono, a te, których nie jest pewn{A?y|a}, kolorem, który podobno nie istnieje, jak twierdzi {B}."),
]
POOLS["amb_gardener"] = [
    ("*", "*", "{A}, the {A_role}, finds a worm and shows it to everyone with the pride of a parent. {B} asks if it can be eaten.",
     "{A}, {A_role}, znajduje dżdżownicę i pokazuje ją wszystkim z dumą rodzica. {B} pyta, czy da się ją zjeść."),
    ("*", "n", "{A} covers the seedlings with old cups against the frost. The camp drinks from the remaining ones and does not complain.",
     "{A} przykrywa siewki starymi kubkami przed mrozem. Obóz pije z tych, które zostały, i nie narzeka."),
]
POOLS["amb_radio"] = [
    ("W", "*", "{A}, the {A_role}, hears a voice in the static, three words, and spends the evening trying to make them into a sentence.",
     "{A}, {A_role}, słyszy w trzaskach głos, trzy słowa, i spędza wieczór, próbując ułożyć z nich zdanie."),
    ("W", "g", "{A} repairs the antenna with wire from a coat hanger and a prayer, and for an hour the camp hears the world again.",
     "{A} naprawia antenę drutem z wieszaka i modlitwą i przez godzinę obóz znów słyszy świat."),
    ("S", "*", "{A}, the {A_role}, finishes a pattern three hands wide and hangs it in the long house. Nobody speaks of it; everyone looks at it.",
     "{A}, {A_role}, kończy wzór szeroki na trzy dłonie i wiesza go w długim domu. Nikt o nim nie mówi; wszyscy na niego patrzą."),
]
POOLS["amb_kid"] = [
    ("*", "*", "{A}, the {A_role}, has decided the camp's cat is a general and issues its orders at supper. {B} says the cat has not objected.",
     "{A}, {A_role}, uznał{A?|a}, że obozowy kot jest generałem, i przy kolacji ogłasza jego rozkazy. {B} mówi, że kot się nie sprzeciwił."),
]
POOLS["amb_elder"] = [
    ("*", "*", "{A}, the {A_role}, corrects {B}'s knot without looking up. {B} sighs and ties it again.",
     "{A}, {A_role}, poprawia węzeł {B?jego|jej} bez podnoszenia wzroku. {B} wzdycha i wiąże go jeszcze raz."),
]

# ---- ticker: more phrasings per trait / job and a line per role
POOLS["f_trait:stubborn"] = [("*", "n", "{A} has dug in over the water barrel, and the barrel has not moved either.", "{A} zaparł{A?|a} się w sprawie beczki z wodą, a beczka też się nie ruszyła.")]
POOLS["f_trait:joker"] = [("*", "g", "{A} has put a boot on the gate post, a hat on the boot, and is waiting for someone to notice.", "{A} położył{A?|a} but na słupku bramy, a na bucie kapelusz, i czeka, aż ktoś zauważy.")]
POOLS["f_trait:quiet"] = [("*", "n", "{A} nods at the right moment and says nothing, and somehow everyone feels heard.", "{A} kiwa głową w odpowiednim momencie i nic nie mówi, a jednak wszyscy czują się wysłuchani.")]
POOLS["f_trait:superstitious"] = [("*", "n", "{A} has hung a small bundle of herbs over the door, and nobody has dared take it down.", "{A} powiesił{A?|a} nad drzwiami mały pęk ziół i nikt nie ośmielił się go zdjąć.")]
POOLS["f_trait:generous"] = [("*", "n", "{A} gave {A_his} spare socks to someone who did not ask, and is pretending not to be cold.", "{A} oddał{A?|a} zapasowe skarpety komuś, kto nie prosił, i udaje, że nie marznie.")]
POOLS["f_trait:hoarder"] = [("*", "*", "{A} says the broken lamp might come in useful, and carries it back to the bunk.", "{A} twierdzi, że zepsuta lampa może się przydać, i niesie ją z powrotem na pryczę.")]
POOLS["f_trait:hothead"] = [("*", "b", "{A} is not in a mood to be spoken to, and the camp has noticed.", "{A} nie ma humoru na rozmowy i obóz to zauważył.")]
POOLS["f_trait:tinkerer"] = [("*", "n", "{A} has three screws left over, and a theory.", "{A} ma trzy śrubki w zapasie i teorię.")]
POOLS["f_trait:storyteller"] = [("*", "*", "{A} begins a story with 'You would not believe,' and the camp pulls its chairs closer.", "{A} zaczyna opowieść od „Nie uwierzycie” i obóz przysuwa krzesła.")]
POOLS["f_trait:nervous"] = [("*", "n", "{A} has been counting the same sacks all morning.", "{A} od rana liczy te same worki.")]
POOLS["f_trait:optimist"] = [("*", "*", "{A} says the rain is good for the garden, the cold is good for the soul, and the soup is good.", "{A} mówi, że deszcz jest dobry dla ogrodu, mróz dla duszy, a zupa dobra.")]
POOLS["f_trait:grumbler"] = [("*", "*", "{A} has a complaint ready for whoever asks, and for several who did not.", "{A} ma gotowe zażalenie dla każdego, kto zapyta, i dla kilku, którzy nie pytali.")]
POOLS["f_job"] = [
    ("*", "*", "{A} {job}, and still checks the weather the way people did then.", "{A} {job} i wciąż sprawdza pogodę tak, jak wtedy."),
    ("*", "n", "In another life, {A} {job}. {A_He} does not miss it, {A_he} says, a little too quickly.", "W innym życiu {A} {job}. Nie tęskni, mówi {A?on|ona}, odrobinę zbyt szybko."),
    ("*", "g", "Ask {A} about the time {A_he} {job} and bring a chair.", "Zapytaj {A} o czasy, gdy {A?on|ona} {job}, i przynieś krzesło."),
    ("*", "*", "{A} {job}, and says it taught {A_him} patience. It is the only thing it taught.", "{A} {job} i mówi, że to nauczyło {A?go|ją} cierpliwości. Tylko tego."),
]
POOLS["f_role:scavenger"] = [("*", "*", "{A} is out looking for something useful, as always.", "{A} wysz{A?edł|ła} poszukać czegoś przydatnego, jak zawsze."),
                             ("*", "n", "{A} has a bag over {A_his} shoulder and a look that says there is something out there.", "{A} ma torbę na ramieniu i minę, która mówi, że gdzieś tam coś jest.")]
POOLS["f_role:medic"] = [("*", "*", "{A} counts the bandages again.", "{A} znów liczy bandaże."), ("*", "n", "{A} washes {A_his} hands for the third time this hour.", "{A} myje ręce po raz trzeci w tej godzinie.")]
POOLS["f_role:cook"] = [("*", "*", "{A} stirs the pot and does not look up.", "{A} miesza w garnku i nie podnosi wzroku."), ("*", "n", "{A} is deciding what counts as dinner tonight.", "{A} decyduje, co dziś uchodzi za kolację.")]
POOLS["f_role:guard"] = [("*", "*", "{A} walks the fence line, slowly.", "{A} obchodzi ogrodzenie, powoli."), ("*", "g", "{A} is on watch, and the camp sleeps a little better for it.", "{A} stoi na warcie, a obóz śpi dzięki temu trochę spokojniej.")]
POOLS["f_role:mechanic"] = [("*", "*", "{A} has grease to the elbows and a smile.", "{A} ma smar po łokcie i uśmiech."), ("*", "n", "{A} is fixing something that was not broken, yet.", "{A} naprawia coś, co jeszcze się nie zepsuło.")]
POOLS["f_role:scout"] = [("*", "*", "{A} is checking the trip lines on the south road.", "{A} sprawdza linki na południowej drodze."), ("*", "n", "{A} is up on the ridge with the binoculars.", "{A} jest na grzbiecie z lornetką.")]
POOLS["f_role:gardener"] = [("*", "*", "{A} is on {A_his} knees in the garden, whispering to the beans.", "{A} klęczy w ogrodzie i szepcze do fasoli."), ("*", "n", "{A} is counting the seedlings, twice.", "{A} liczy siewki, dwa razy.")]
POOLS["f_role:kid"] = [("*", "*", "{A} is running somewhere, loudly.", "{A} gdzieś biegnie, głośno."), ("*", "n", "{A} asks why, for the fortieth time today.", "{A} pyta dlaczego, po raz czterdziesty dziś.")]
POOLS["f_role:elder"] = [("*", "*", "{A} is in the best chair, telling anyone who will listen how it used to be.", "{A} siedzi w najlepszym fotelu i opowiada każdemu, kto posłucha, jak to dawniej było."),
                         ("*", "n", "{A} naps, and the camp walks softly.", "{A} drzemie, a obóz chodzi na palcach.")]
POOLS["f_role:radio"] = [("W", "*", "{A} is turning the dial, patiently.", "{A} cierpliwie kręci gałką."), ("W", "n", "{A} listens to the static as if it were speaking.", "{A} słucha trzasków, jakby do {A?niego|niej} mówiły."),
                         ("S", "*", "{A} sits at the loom, humming.", "{A} siedzi przy krośnie i nuci."), ("S", "n", "{A} is weaving a pattern nobody else knows the end of.", "{A} tka wzór, którego końca nikt inny nie zna.")]

POOLS["memorial"] = [
    ("*", "*", "{A} sweeps the bunk where {D} slept, though it is already clean. Then {A_he} sits on it.",
     "{A} zamiata miejsce, gdzie spał{D?|a} {D}, choć jest już czyste. Potem na nim siada."),
    ("*", "n", "Nobody wants to sing tonight, so {A} hums {D}'s favorite tune, and somebody, somewhere in the dark, joins in.",
     "Nikomu dziś nie chce się śpiewać, więc {A} nuci melodię, którą lubił{D?|a} {D}, a ktoś w ciemności się dołącza."),
    ("*", "b", "{D}'s handwriting is still on a crate, and {A} cannot bring {A_himself} to move it. {A_He} leaves it where it is.",
     "Pismo, które zostawił{D?|a} {D}, wciąż widać na skrzyni; {A} nie jest w stanie jej ruszyć i zostawia ją, gdzie jest."),
    ("*", "g", "{A} plants something small by the north wall for {D}. Nobody asks what it is; everyone waters it.",
     "{D}: {A} sadzi coś małego przy północnym murze. Nikt nie pyta co; wszyscy to podlewają."),
]
POOLS["arrive"] += [
    ("*", "*", "{A} gets the grand tour: {B} shows {A_him} where the water is, where the latrine is, and where, on no account, to stand during a drill.",
     "{A} dostaje oprowadzanie: {B} pokazuje {A?mu|jej}, gdzie jest woda, gdzie latryna i gdzie w żadnym wypadku nie stawać podczas alarmu."),
    ("*", "*", "{A} says very little about where {A_he} was before. {B} says even less, which {A} seems to like.",
     "{A} niewiele mówi o tym, gdzie był{A?|a} wcześniej. {B} mówi jeszcze mniej, co {A?mu|jej} chyba odpowiada."),
    ("*", "n", "A new pair of hands: {A}, who {job}. By evening {A_he} has an opinion about the soup.",
     "Nowa para rąk: {A}, {A?który|która} {job}. Do wieczora {A?on|ona} ma już zdanie o zupie."),
]
POOLS["tr_meet"] = [
    ("*", "*", "{A} lays the goods on the ground and {grp} lay theirs down. Then everyone looks at everyone else's, which takes an hour.",
     "{A} kładzie towar na ziemi, a {grp_nom} kładą swój. Potem wszyscy oglądają towar innych, co zajmuje godzinę."),
    ("*", "g", "{A} and {B} meet {grp} at {dest} and agree on a price before anyone sits down, which both sides take as a good sign.",
     "{A} i {B} spotykają {grp_acc} {dest_at} i uzgadniają cenę, zanim ktokolwiek usiądzie, co obie strony uznają za dobry znak."),
]

# ---- ticker tails: a short aside after a fact line (only when the line + tail still fit the one-line widget), by mood and by weather
POOLS["f_tail"] = [
    ("*", "*", "It is the small things.", "To drobiazgi."),
    ("*", "*", "Nobody comments.", "Nikt tego nie komentuje."),
    ("*", "*", "Somebody should write this down.", "Ktoś powinien to zapisać."),
    ("*", "*", "That is how it goes here.", "Tak tu bywa."),
    ("*", "*", "Life goes on, loudly.", "Życie toczy się dalej, głośno."),
    ("*", "*", "It could be worse.", "Mogłoby być gorzej."),
    ("*", "*", "Same as yesterday, nearly.", "Prawie jak wczoraj."),
    ("*", "*", "Nobody is surprised.", "Nikogo to nie dziwi."),
    ("*", "*", "At least it is something.", "Przynajmniej coś."),
    ("*", "n", "The day is long.", "Dzień jest długi."),
    ("*", "n", "Nobody asks for more.", "Nikt nie prosi o więcej."),
    ("*", "g", "Spirits are good today.", "Humory dziś dopisują."),
    ("*", "g", "It is a good day for it.", "To dobry dzień na takie rzeczy."),
    ("*", "g", "People are smiling, mostly.", "Ludzie się uśmiechają, w większości."),
    ("*", "b", "Nobody looks up.", "Nikt nie podnosi wzroku."),
    ("*", "b", "Everyone is tired.", "Wszyscy są zmęczeni."),
    ("*", "b", "It does not help much.", "Niewiele to pomaga."),
]
POOLS["f_tail_rain"] = [("*", "*", "The rain does not help.", "Deszcz wcale nie pomaga."), ("*", "*", "Everything is wet.", "Wszystko jest mokre."), ("*", "*", "Rain on the roof, all day.", "Deszcz na dachu, cały dzień.")]
POOLS["f_tail_fog"] = [("*", "*", "The fog does not care.", "Mgła się tym nie przejmuje."), ("*", "*", "Fog at the gate.", "Mgła przy bramie.")]
POOLS["f_tail_cold"] = [("*", "*", "Cold enough to see your breath.", "Zimno aż para idzie z ust."), ("*", "*", "Hands are cold, tempers are not.", "Ręce zimne, humory nie.")]
POOLS["f_tail_clear"] = [("*", "*", "At least the sky is clear.", "Przynajmniej niebo jest czyste."), ("*", "g", "The sun is out for once.", "Słońce wyszło, na jedną chwilę.")]
POOLS["f_tail_smoke"] = [("*", "*", "The air tastes of smoke.", "W powietrzu czuć dym.")]
POOLS["f_tail_wind"] = [("*", "*", "The wind carries every word off.", "Wiatr roznosi każde słowo.")]
