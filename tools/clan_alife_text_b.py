"""A-Life text pools, part B: rations politics, relationships, newcomers, the dead remembered, the sick cared for.  Row format: see clan_alife_text_a.py."""

POOLS = {}

# ---- a day in deficit (the real tally: sup supplies in, need needed): A and B argue about shares
POOLS["rat_deficit"] = [
    ("*", "*", "The tally says {sup} against {need}. {A} and {B} argue over how thin to cut the bowls.",
     "Bilans dnia: {sup} z {need} potrzebnych. {A} i {B} kłócą się o to, jak cienko pokroić porcje."),
    ("*", "b", "{sup} in, {need} needed. {A} wants the watch fed first; {B} wants the children fed first; everybody wants to be fed.",
     "Wpłynęło {sup}, potrzeba {need}. {A} chce nakarmić najpierw wartę, {B} dzieci, a wszyscy chcą po prostu jeść."),
    ("*", "*", "Short again: {sup} where {need} were needed. {A} stands at the pot with the ladle and does not look up.",
     "Znów za mało: {sup}, a trzeba było {need}. {A} stoi przy garnku z chochlą i nie podnosi wzroku."),
    ("W", "*", "{sup} against {need} on the quartermaster's board. {A} says ration cards should be halved for the rear details. {B} says that is easy to say with a full stomach.",
     "Na tablicy kwatermistrza: {sup} wobec {need}. {A} twierdzi, że karty żywnościowe na zapleczu trzeba ściąć o połowę. {B} odpowiada, że łatwo to mówić z pełnym brzuchem."),
    ("S", "*", "{sup} where {need} were needed. At the long table {A} reminds everyone that want is a teacher; {B} reminds {A} that teachers eat first.",
     "{sup}, a potrzeba {need}. Przy długim stole {A} przypomina, że niedostatek jest nauczycielem, a {B} przypomina, że nauczyciele jedzą pierwsi."),
    ("*", "b", "{A} is caught with a second piece of bread. {B} does not shout. That is worse.",
     "{A} zostaje przyłapan{A?y|a} z drugim kawałkiem chleba. {B} nie krzyczy. To gorsze."),
    ("*", "n", "A day short: {sup} in, {need} needed. {A} and {B} cut the portions in half and the argument in three.",
     "Dzień na minusie: {sup} z {need}. {A} i {B} dzielą porcje na pół, a kłótnię na trzy."),
    ("*", "b", "Somebody has been hiding food. {A} says it was not {A_him}. {B} says nobody said it was.",
     "Ktoś chowa jedzenie. {A} mówi, że to nie {A?on|ona}. {B} mówi, że nikt tak nie twierdził."),
]
# ---- a day with a surplus
POOLS["rat_surplus"] = [
    ("*", "*", "The tally says {sup} for {need} needed. {A} ladles the bowls full for once, and {B} stands guard over the pot so nobody sneaks seconds.",
     "Bilans dnia: {sup} przy {need} potrzebnych. {A} nalewa miski do pełna, a {B} pilnuje garnka, żeby nikt nie dobierał dokładki."),
    ("*", "g", "{sup} in, {need} needed, and it shows: {A} sings off-key at the cook fire and nobody tells {A_him} to stop.",
     "Wpłynęło {sup}, potrzeba {need}, i to widać: {A} fałszuje przy ogniu, a nikt nie każe {A?mu|jej} przestać."),
    ("*", "*", "A good day: {sup} against {need}. {B} suggests putting a little aside for the lean days; {A} says that is exactly why {A_he} likes {B}.",
     "Dobry dzień: {sup} wobec {need}. {B} proponuje odłożyć trochę na chude dni, a {A} mówi, że właśnie za to {B?go|ją} lubi."),
    ("W", "*", "The quartermaster's board reads {sup} to {need}. {A} gets an extra ladle for the watch, and the watch behaves for an entire evening.",
     "Tablica kwatermistrza: {sup} do {need}. {A} dostaje dodatkową chochlę dla warty, a warta zachowuje się przez cały wieczór."),
    ("S", "*", "{sup} for {need} needed. The long house sets a second bowl at every place, and {A} gives thanks so quietly that only {B} hears.",
     "{sup} przy {need} potrzebnych. W długim domu przy każdym miejscu staje druga miska, a {A} dziękuje tak cicho, że słyszy to tylko {B}."),
    ("*", "g", "Full pots, {sup} to {need}. {B} bakes something with the last of the flour, and the whole camp finds a reason to walk past.",
     "Pełne garnki, {sup} do {need}. {B} piecze coś z ostatniej mąki, a cały obóz znajduje powód, żeby tamtędy przejść."),
]
# ---- weeks of plenty / of want in a row (ds / ss streak)
POOLS["rat_streak_good"] = [
    ("*", "*", "Three good days in a row. {A} has started to say the word 'winter' out loud again, and nobody flinches.",
     "Trzy dobre dni z rzędu. {A} znów zaczyna mówić słowo „zima” na głos i nikt się nie wzdryga."),
    ("*", "g", "The clan has eaten well for days. {A} notices {B} laughing, and writes it down, because it has been a while.",
     "Klan od dni je do syta. {A} zauważa, że {B} się śmieje, i zapisuje to, bo minęło sporo czasu."),
    ("*", "*", "Nobody has gone to bed hungry this week. {A} touches the table twice, for luck.",
     "W tym tygodniu nikt nie położył się głodny. {A} dwa razy stuka w stół na szczęście."),
]
POOLS["rat_streak_bad"] = [
    ("*", "b", "Hunger is getting into everything. {A} and {B} snap at each other over a spoon, and both of them know it was not about the spoon.",
     "Głód wchodzi we wszystko. {A} i {B} kłócą się o łyżkę i oboje wiedzą, że nie chodziło o łyżkę."),
    ("*", "b", "Another thin day. {A} has stopped counting the days and started counting the people at the table.",
     "Kolejny chudy dzień. {A} przestał{A?|a} liczyć dni i zacz{A?ął|ęła} liczyć ludzi przy stole."),
    ("*", "*", "Nobody talks during the meal now. {B} says it is to save energy. {A} says it is to save {A_him} from the answer.",
     "Podczas posiłku nikt już nie rozmawia. {B} mówi, że to dla oszczędzania sił. {A} mówi, że to po to, żeby oszczędzić sobie odpowiedzi."),
]

# ---- relationships: A, B
POOLS["friend"] = [
    ("*", "*", "{A} and {B} have taken to sharing a watch. They say it is for the company; they mean it is for the silences.",
     "{A} i {B} zacz{AB?ęli|ęły} dzielić wartę. Mówią, że dla towarzystwa; mają na myśli, że dla ciszy."),
    ("*", "g", "{A} and {B} trade bad jokes across the yard until somebody throws a boot. Both of them are grinning.",
     "{A} i {B} wymieniają się kiepskimi żartami przez podwórze, aż ktoś rzuca butem. Oboje się szczerzą."),
    ("*", "*", "{B} saves {A} the last dry spot by the fire, and pretends it was an accident.",
     "{B} zostawia ostatnie suche miejsce przy ogniu, zajmuje je {A}, a {B} udaje, że to przypadek."),
]
POOLS["quarrel"] = [
    ("*", "*", "{A} and {B} had words over a missing knife. The knife turned up in {A}'s boot. Nobody has apologised yet.",
     "{A} i {B} pokłóci{AB?li|ły} się o zgubiony nóż. Nóż znalazł się w {A?jego|jej} bucie. Nikt jeszcze nie przeprosił."),
    ("*", "b", "{A} and {B} are not speaking. The rest of the clan has started to speak around them, which is more tiring than the silence.",
     "{A} i {B} ze sobą nie rozmawiają. Reszta klanu zaczęła rozmawiać wokół nich, co męczy bardziej niż cisza."),
    ("W", "*", "{A} and {B} nearly come to blows over the radio dial. The watch commander sends them both to clean the latrine, together.",
     "{A} i {B} omal nie biją się o gałkę radia. Dowódca warty wysyła ich obu do sprzątania latryny, razem."),
    ("S", "*", "{A} and {B} dispute a verse during the evening reading and cannot agree on which of them is wrong. The elders let them dispute.",
     "{A} i {B} spierają się podczas wieczornego czytania o jeden werset i nie mogą ustalić, które z nich się myli. Starsi pozwalają im się spierać."),
    ("*", "n", "{A} and {B} quarrel over whose turn it was to haul water. Neither of them hauled water. The barrel is empty.",
     "{A} i {B} kłócą się o to, czyja kolej na noszenie wody. Żadne nie poszło po wodę. Beczka jest pusta."),
]
POOLS["reconcile"] = [
    ("*", "*", "{A} and {B} are talking again. It started over a shared bowl; nobody asked how.",
     "{A} i {B} znów ze sobą rozmawiają. Zaczęło się od wspólnej miski; nikt nie pytał jak."),
    ("*", "g", "{A} carves a small thing out of scrap and leaves it at {B}'s place. {B} wears it all day. That is the apology.",
     "{A} struga coś małego ze skrawka drewna i zostawia przy {B?jego|jej} miejscu. {B} nosi to przez cały dzień. To są przeprosiny."),
    ("*", "*", "The quarrel between {A} and {B} is over. They agree on one thing at least: never to speak of it again.",
     "{A} i {B} już się nie kłócą. W jednym są zgodni: nigdy więcej o tym nie mówić."),
    ("*", "n", "{B} brings {A} a mug of something hot and sits down without a word. {A} moves over.",
     "{B} przynosi {A?mu|jej} kubek czegoś gorącego i siada bez słowa. {A} się przesuwa."),
    ("*", "b", "After all that has happened, {A} and {B} shake hands. It is a short handshake. It holds.",
     "Po tym wszystkim, co się stało, {A} i {B} ściskają sobie dłonie. To krótki uścisk. Trzyma."),
]
POOLS["mentor"] = [
    ("*", "*", "{A} is teaching {B} to {skill}. {B} is a poor student and a stubborn one, which works out about even.",
     "{A} uczy, a {B} próbuje {skill}. {B} jest {B?kiepskim uczniem|kiepską uczennicą} i {B?upartym|upartą}, co mniej więcej się równoważy."),
    ("*", "*", "{B} asks {A} how to {skill}. {A} says it takes years, and starts the lesson anyway.",
     "{B} podchodzi do {A?niego|niej} z pytaniem, jak {skill}. {A} mówi, że to wymaga lat, i mimo to zaczyna lekcję."),
    ("*", "g", "{A} watched {B} {skill} today, start to finish, without correcting once. Both of them looked a little surprised.",
     "{A} patrzył{A?|a}, jak {B} dziś potrafi {skill}, od początku do końca, ani razu nie poprawiając. Oboje wyglądali na lekko zaskoczonych."),
    ("*", "n", "{A} makes {B} {skill} again and again beside a quiet stretch of wall. The wall is learning patience.",
     "{A} każe ćwiczyć w kółko przy spokojnym kawałku muru, a {B} ma {skill}. Mur uczy się cierpliwości."),
    ("*", "*", "Lesson of the day: {skill}. {A} teaches, {B} fails, {A} teaches again. By evening there is progress, or at least fewer bruises.",
     "Lekcja dnia: {skill}. {A} uczy, {B} zawodzi, {A} uczy jeszcze raz. Do wieczora widać postęp albo przynajmniej mniej siniaków."),
    ("*", "b", "Even now, {A} makes time to show {B} how to {skill}. It is a way of saying there will be a later.",
     "{B}: nawet teraz {A} znajduje czas, żeby pokazać {B?mu|jej}, jak {skill}. To sposób, by powiedzieć, że będzie jakieś później."),
]
POOLS["romance"] = [
    ("*", "*", "{A} and {B} keep finding reasons to be on the same shift. The rest of the clan keeps finding reasons not to mention it.",
     "{A} i {B} ciągle znajdują powody, żeby być na tej samej zmianie. Reszta klanu ciągle znajduje powody, żeby o tym nie wspominać."),
    ("*", "g", "{A} and {B} were seen on the roof at dusk, not talking. Everybody pretends to be too busy to look.",
     "Widziano, jak {A} i {B} siedzą o zmierzchu na dachu i nie rozmawiają. Wszyscy udają, że są zbyt zajęci, żeby patrzeć."),
    ("*", "*", "{B} has started saving the better half of the bread for {A}. {A} has started noticing.",
     "{B} zacz{B?ął|ęła} odkładać lepszą połowę chleba dla {A?niego|niej}. {A} zacz{A?ął|ęła} to zauważać."),
    ("*", "b", "In the dark, {A} and {B} sit very close. Nobody asks what it means. It means they are not alone.",
     "W ciemności {A} i {B} siedzą bardzo blisko. Nikt nie pyta, co to znaczy. To znaczy, że nie są sami."),
    ("*", "n", "{A} cut {B}'s hair by the fire, slowly, with more attention than the job needed.",
     "{A} ścinał{A?|a} włosy, a {B} siedział{B?|a} przy ogniu; powoli, powoli, z większą uwagą, niż wymagała ta robota."),
]

# ---- a newcomer (the real join of the day): A the newcomer, B a welcomer, orig, job
POOLS["arrive"] = [
    ("*", "*", "It turns out {A} {job} before the outbreak, and {B} has already found a use for it.",
     "Okazuje się, że {A} przed epidemią {job}, a {B} już znalazł{B?|a} na to zastosowanie."),
    ("*", "*", "{A} spent the winter {orig}, {A_he} says, before finding the clan. {B} nods like {B_he} has heard worse.",
     "{A} przezimował{A?|a} {orig}, jak mówi, zanim znalazł{A?|a} klan. {B} kiwa głową, jakby słyszał{B?|a} gorsze rzeczy."),
    ("*", "g", "{A} is quiet at the fire, but {B} gets one story out of {A_him}: months {orig}, and a great deal of luck.",
     "{A} milczy przy ogniu, ale {B} wyciąga z {A?niego|niej} jedną historię: miesiące {orig} i mnóstwo szczęścia."),
    ("*", "b", "{A} does not talk about the time {orig}. {B} does not ask. Both of them eat.",
     "{A} nie mówi o tym, co było {orig}. {B} nie pyta. Oboje jedzą."),
    ("*", "n", "{B} puts {A} to work: {A} {job}, after all, and that counts for something here.",
     "{B} daje {A?mu|jej} robotę: {A} przecież {job}, a tu to się liczy."),
    ("*", "*", "Whatever {A} lived through {orig}, {A_he} carries it quietly. {B} gives {A_him} the better blanket.",
     "{A} nosi w sobie to, co przeżył{A?|a} {orig}, po cichu. {B} daje {A?mu|jej} lepszy koc."),
]
POOLS["arrive_follow"] = [
    ("*", "g", "{A} laughed at supper tonight, the first time since coming. {B} pretends not to have seen it.",
     "{A} zaśmiał{A?|a} się dziś przy kolacji, pierwszy raz od przybycia. {B} udaje, że tego nie widział{B?|a}."),
    ("*", "*", "{A} has taken the empty bunk by the wall. Slowly, the bunk is starting to look lived in.",
     "{A} zaj{A?ął|ęła} wolną pryczę przy ścianie. Powoli prycza zaczyna wyglądać na zamieszkaną."),
    ("*", "b", "{A} sleeps with boots on, still. {B} stops telling {A_him} it is safe here, because nobody here believes it either.",
     "{A} wciąż śpi w butach. {B} przestaje mówić {A?mu|jej}, że tu jest bezpiecznie, bo nikt tu w to nie wierzy."),
    ("*", "n", "{B} puts {A} on the water run. It is the clan's way of finding out who someone is.",
     "{A} trafia na wartę przy wodzie: {B} wpisuje {A?go|ją} na listę. To sposób klanu, żeby sprawdzić, kim ktoś jest."),
    ("W", "*", "{A} has been given a name tag and a rifle number. It is the only official thing about the clan, and {A_he} wears it like a medal.",
     "{A} dostał{A?|a} numer karabinu. To jedyna oficjalna rzecz w klanie, a {A?on|ona} nosi ją jak medal."),
]

# ---- the dead remembered: A mourner (alive), D dead, keep
POOLS["memorial"] = [
    ("*", "*", "{A} wraps {D}'s {keep} in a clean cloth and puts it where everyone can see it. Nobody says why.",
     "{A} owija w czystą szmatkę to, co zostało po zmarł{D?ym|ej} ({D}: {keep_nom}), i kładzie w widocznym miejscu. Nikt nie pyta po co."),
    ("*", "b", "There is a gap at the table where {D} used to sit. {A} stands in it for a moment before sitting down next to it.",
     "Przy stole zostało puste miejsce, gdzie siadywał{D?|a} {D}. {A} stoi w nim chwilę, zanim usiądzie obok."),
    ("*", "*", "{A} takes over {D}'s chores without being asked. {A_He} does them badly, and nobody dares to say so.",
     "{A} przejmuje bez proszenia obowiązki, które miał{D?|a} {D}. Wykonuje je kiepsko i nikt nie ma odwagi tego powiedzieć."),
    ("*", "*", "{A} sat up late with {D}'s {keep}, turning it over in {A_his} hands. At dawn, {A_he} put it down gently.",
     "{A} siedział{A?|a} do późna z pamiątką ({D}: {keep_nom}), obracając pamiątkę w dłoniach. O świcie odłożył{A?|a} ją delikatnie."),
    ("W", "*", "{A} scratches {D}'s name into the wall of the barracks, below the others. The list is longer than anyone wants to read.",
     "{A} wydrapuje imię {D} na ścianie koszar, pod innymi. Lista jest dłuższa, niż ktokolwiek chce czytać."),
    ("S", "*", "{A} ties a thread of {D}'s color to the shore post, where the wind will take the prayers out over the water.",
     "{A} przywiązuje nitkę w kolorze, który {D?lubił|lubiła} {D}, do słupa na brzegu, żeby wiatr poniósł modlitwy nad wodę."),
    ("*", "g", "{A} tells the story of the first time {A_he} met {D}, and for once nobody leaves the fire. They laugh in the right places.",
     "Imię {D} wraca przy ogniu: {A} opowiada, jak {D?go|ją} poznał{A?|a}, i tym razem nikt nie odchodzi. Śmieją się w odpowiednich miejscach."),
    ("*", "n", "{A} still counts {D} when counting heads, and corrects the count out loud, every time.",
     "Liczy głowy: {A} wciąż dolicza {D?jego|ją}, czyli {D}, i za każdym razem poprawia się na głos."),
]
POOLS["memorial_late"] = [
    ("*", "*", "Someone has been leaving a small stone on {D}'s bunk. {A} knows who it is, and does not ask.",
     "Ktoś zostawia mały kamień na pryczy, na której spał{D?|a} {D}. {A} wie kto, i nie pyta."),
    ("*", "*", "{A} wears {D}'s {keep} today. It does not fit, {A_he} says, and does not take it off.",
     "{A} nosi dziś pamiątkę ({D}: {keep_nom}). Nie pasuje, mówi {A}, i nie zdejmuje."),
    ("*", "b", "Nobody mentions {D} anymore, which is how the clan knows how much it hurts. {A} breaks the rule and says the name once.",
     "Imię {D} przestało padać przy ogniu i po tym klan wie, jak bardzo boli. {A} łamie zasadę i raz je wypowiada."),
    ("*", "*", "A week since {D}. {A} is sleeping through the night again, and feels guilty about it, and sleeps anyway.",
     "Minął tydzień, odkąd od{D?szedł|eszła} {D}. {A} znów przesypia noc, czuje się winn{A?y|a} i mimo to śpi."),
]

# ---- the sick cared for (the real sick: A is sick with ill, B tends A; B is the medic when the clan has one)
POOLS["vigil"] = [
    ("*", "*", "{B} sits up with {A} again tonight, a wet cloth and a cup of water. {A} has {ill_a}, and the nights are the worst of it.",
     "{B} znów czuwa dziś przy {A?nim|niej} z mokrą szmatką i kubkiem wody. {A} ma {ill_acc}, a noce są najgorsze."),
    ("*", "b", "{B} changes {A}'s bandages and does not say what {B_he} sees. {A} reads it in {B}'s face anyway.",
     "{B} zmienia {A?mu|jej} opatrunki i nie mówi, co widzi. {A} i tak czyta to z {B?jego|jej} twarzy."),
    ("*", "*", "{B}, the {B_role}, counts the pills left for {A}'s {ill} and counts them again, as if the number would change.",
     "{B}, {B_role}, liczy tabletki, które zostały dla chorego ({A}, {ill}), i liczy je jeszcze raz, jakby liczba miała się zmienić."),
    ("W", "*", "{B} radios the stadium for {cure} for {A}. The answer is in static, and then there is no answer.",
     "{B} wzywa przez radio stadion po {cure_acc}, bo {A} ich potrzebuje. Odpowiedź jest w trzaskach, a potem nie ma żadnej."),
    ("S", "*", "{B} prays at {A}'s bedside, then boils willow bark when the praying is done. {A} has {ill_a}.",
     "{B} modli się przy {A?jego|jej} łóżku, a po modlitwie parzy korę wierzby. {A} ma {ill_acc}."),
    ("*", "*", "The cough from {A}'s corner has changed. {B} noticed it first and pretends not to have.",
     "Kaszel z kąta, gdzie leży {A}, się zmienił. {B} zauważył{B?|a} to pierwsz{B?y|a} i udaje, że nie."),
    ("*", "g", "{A} is awake and asking for soup. {B} says that is a good sign and goes to find some, quickly.",
     "{A} nie śpi i prosi o zupę. {B} mówi, że to dobry znak, i szybko idzie jej poszukać."),
]
POOLS["recovered"] = [
    ("*", "g", "{A} is out of bed and complaining about the food, which is the best news the clan has had all week.",
     "{A} wstał{A?|a} z łóżka i narzeka na jedzenie, co jest najlepszą wiadomością tygodnia."),
    ("*", "*", "{B} burns the last of {A}'s bedding and watches the smoke. {A} is going to live, and has said so.",
     "{B} pali ostatnie z pościeli {A?jego|jej} i patrzy na dym. {A} będzie żyć i sam{A?|a} to powiedział{A?|a}."),
    ("*", "b", "{A} walked to the fire on {A_his} own legs today. Nobody cheered. Everyone moved over to make room.",
     "{A} dosz{A?edł|ła} dziś do ognia o własnych siłach. Nikt nie wiwatował. Wszyscy się przesunęli, żeby zrobić miejsce."),
    ("*", "n", "The fever is gone, and {A} asks what {A_he} missed. {B} says nothing, and then, after a pause, everything.",
     "Gorączka minęła, a {A} pyta, co {A?go|ją} ominęło. {B} nic nie mówi, a potem, po chwili, wszystko."),
]
