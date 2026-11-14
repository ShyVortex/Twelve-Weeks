"""Text of the clan story arcs (tools/clan_arcs.py): one entry per arc node, EN + PL side by side.

TEXT["<arc>.<node>"] = (headline EN, headline PL, vignette EN, vignette PL).  The headline is shown in capitals after "DAY n:" (the feed row's first sentence, so the
one-line in-game widget shows it whole); the vignette is 1-3 sentences.  People: {A} protagonist, {B} the bonded one; English {A_he} {A_his} {A_him} {A_himself};
Polish switches {A?on|ona}, {A?ł|ła}, {AB?li|ły} (feminine plural only when all named are women); the Polish never declines a name (a name stays in the nominative).
Variables: {rel} (EN: what A is to B: sister, mentor ...) {rel_nom} {rel_acc} {rel_gen} (PL), {task} {place} {wish} {keep} {keep_acc} {keep_ins} {keep_gen} {thing} {map}
{enemy} {enemies} {enemy_gen} {sup} {need}.
"""

TEXT = {
    # ------------------------------------------------------------------------------------------------ a member does not return from a raid
    "missing.n0": ("{A} didn't return from the {task}", "{A} nie wrócił{A?|a} z {task}",
                   "The evening count came up one short. {B} waited at the gate until the lamps were put out.",
                   "Wieczorny apel wyszedł o jedną osobę za krótko. {B} czekał{B?|a} przy bramie, aż pogaszono lampy."),
    "missing.search": ("{B}, worried for {B_his} {rel}, went looking for {A_him}", "{B}, zmartwion{B?y|a} o {rel_acc}, posz{B?edł|ła} {A?go|ją} szukać",
                       "{B} took water, a knife and the shortest way toward the {place}, and told nobody but the gate watch.",
                       "{B} {B?wziął|wzięła} wodę, nóż i najkrótszą drogę w stronę {place_gen}, i nikomu nie powiedział{B?|a} poza wartą przy bramie."),
    "missing.found_dead": ("{B} found {A} at the edge of the {place}", "{B} znalazł{B?|a} {A?go|ją} na skraju {place_gen}",
                    'Too late. {A} had been bitten days ago, the wound black to the elbow, and what was left standing in the rubble had hardly a jaw and no more memory of anyone than a dog has of a road. It came on anyway, dragging a leg that had been broken and walked on.',
                    'Za późno. {A} został{A?|a} ugryziony kilka dni wcześniej, rana czerniała do łokcia, a to, co stało w gruzach, nie miało już prawie szczęki i nikogo już nie pamiętało, tak jak pies nie pamięta drogi. Szło do przodu mimo to, ciągnąc nogę, która była złamana, a jednak chodziła.'),
    "missing.found_gut": ("{B} found {A} against the wall, holding {A_his} own guts in {A_his} hands", "{B} znalazł{B?|a} {A?go|ją} pod ścianą, jak trzymał{A?|a} własne wnętrzności w dłoniach",
                          "{A} looked up with great politeness, as if apologising for the mess, and asked for water. There was no point in refusing and no point in giving it. {B} sat down in the wet and talked about nothing until {A} stopped answering.",
                          "{A} spojrzał{A?|a} w górę z wielką uprzejmością, jakby przepraszał{A?|a} za bałagan, i poprosił{A?|a} o wodę. Nie było sensu odmawiać ani dawać. {B} usiadł{B?|a} w tej wilgoci i mówił{B?|a} o niczym, aż {A} przestał{A?|a} odpowiadać."),
    "missing.mercy_gut": ("{B} stayed until it was over", "{B} został{B?|a} do końca",
                          "It took a long time, longer than a shot would have. {B} carried home what could be carried in a coat, and the rest stayed under the wall with stones on it and a flag that was only a rag.",
                          "Trwało to długo, dłużej, niż trwałby strzał. {B} {B?zaniósł|zaniosła} do domu w płaszczu to, co dało się zanieść, a reszta została pod murem, przykryta kamieniami, z flagą, która była tylko szmatą."),
    "missing.mercy": ("{B} did what had to be done", "{B} zrobił{B?|a} to, co trzeba było zrobić",
                    'One shot in the dark of the garage, and the sound of it went on far too long. {B} put a knife through what was left to be sure, then sat in the mess of it for an hour. {B} buried {A} under the wall and walked home with {A_his} coat over one arm, soaked black down one side.',
                    'Jeden strzał w ciemności garażu, a jego dźwięk trwał stanowczo za długo. {B} wbił{B?|a} jeszcze nóż w to, co zostało, żeby mieć pewność, po czym siedział{B?|a} w tym wszystkim godzinę. {B} pochował{B?|a} {A?go|ją} pod murem i wrócił{B?|a} z {A?jego|jej} płaszczem na ramieniu, czarnym od krwi z jednej strony.'),
    "missing.despair": ("{B} couldn't bring {B_himself} to do it, and decided to stay with {A_him}", "{B} nie potrafił{B?|a} tego zrobić i zdecydował{B?|a} się zostać z {A?nim|nią}",
                    '{B} took off {B_his} glove, pressed a cut palm to the bite, and sat down in the grass holding {A_his} hand while the calling from the wall went unanswered.',
                    '{B} {B?zdjął|zdjęła} rękawicę, {B?przycisnął|przycisnęła} rozciętą dłoń do ugryzienia i usiadł{B?|a} w trawie, trzymając {A?go|ją} za rękę, a wołanie z muru pozostało bez odpowiedzi.'),
    "missing.turned": ("{B} never came back from the {place}", "{B} nie wrócił{B?|a} z {place_gen}",
                    'The watch found two coats folded side by side, one of them soaked through, and a wide dark drag mark leading into the underpass. Nobody followed it. Nobody speaks of it at supper; everyone sets out two bowls too many and takes them away untouched.',
                    'Wartownicy znaleźli dwa płaszcze złożone obok siebie, jeden przemoczony, i szeroki ciemny ślad ciągnięcia prowadzący do tunelu. Nikt za nim nie poszedł. Nikt nie mówi o tym przy kolacji; wszyscy stawiają o dwie miski za dużo i zabierają je nietknięte.'),
    "missing.pulled": ("The watch dragged {B} back by the collar", "Wartownicy przyprowadzili {B} siłą z powrotem",
                    'They tore {B} off by the collar. {B} had a palm cut to the bone on a broken bottle, still red, still only human. {B} fought them, then wept into a sleeve, and has not asked after {A} since.',
                    'Wyrwali {B} za kołnierz. {B} miał{B?|a} dłoń rozciętą do kości o rozbitą butelkę, wciąż czerwoną, wciąż tylko ludzką. Szarpał{B?|a} się z nimi, potem płakał{B?|a} w rękaw i od tamtej pory nikogo o nic nie pyta.'),
    "missing.alive": ("{B} carried {A} home", "{B} {B?przyniósł|przyniosła} {A?go|ją} do domu",
                      "{A} came back with a broken ankle and a story nobody believes yet. {B} has not let go of {A_his} sleeve all evening.",
                      "{A} wrócił{A?|a} ze złamaną kostką i opowieścią, w którą nikt jeszcze nie wierzy. {B} przez cały wieczór nie puszcza {A?jego|jej} rękawa."),
    "missing.alive_late": ("{A} walked in alone at dawn", "{A} wszedł{A?|ła} sam{A?|a} o świcie do obozu",
                           "Thin, filthy, angrier than anything: {A} had waited out two nights in a flooded cellar. {B} was the first at the gate, and the first to shout.",
                           "Chud{A?y|a}, brudn{A?y|a}, wściekł{A?y|a} jak nigdy: {A} przeczekał{A?|a} dwie noce w zalanej piwnicy. {B} był{B?|a} pierwszy{B?|a} przy bramie i pierwszy{B?|a} {B?zaczął|zaczęła} krzyczeć."),

    # ------------------------------------------------------------------------------------------------ a fever
    "sick.s0": ("{A} can't shake the fever", "{A} nie może zbić gorączki",
                "{B} has not left the bunk since midnight. The cloth is changed every hour, and the talk has gone from stories to counting.",
                "{B} {B?nie odszedł|nie odeszła} od pryczy od północy. Okład zmieniany jest co godzinę, a rozmowa przeszła z opowieści w liczenie."),
    "sick.treat": ("{B} used {thing} on {A}", "{B} zużył{B?|a} na {A?niego|nią} {thing}",
                   "It was the one thing in the cupboard that was not a promise. By nightfall the shaking had eased.",
                   "To była jedyna rzecz w szafce, która nie była obietnicą. Przed nocą dreszcze zelżały."),
    "sick.hold": ("{B} kept watch again tonight", "{B} znowu czuwał{B?|a} tej nocy",
                  "Nothing changed, which is not the same as nothing happening. {A} slept in pieces; {B} did not sleep at all.",
                  "Nic się nie zmieniło, co nie znaczy, że nic się nie działo. {A} spał{A?|a} kawałkami; {B} nie spał{B?|a} wcale."),
    "sick.recover": ("{A} stood up on {A_his} own", "{A} wsta{A?ł sam|ła sama}",
                     "{A} asked for bread, and for the first time in days meant it. {B} turned away to hide a face that was doing something complicated.",
                     "{A} poprosił{A?|a} o chleb i pierwszy raz od dni naprawdę go chciał{A?|a}. {B} odwrócił{B?|a} się, żeby ukryć twarz, która robiła coś skomplikowanego."),
    "sick.death": ("{B} sat with {A} until the end", "{B} siedział{B?|a} przy {A?nim|niej} do końca",
                    'It was not quiet. {A} coughed up what the fever had made of the lungs, and the bowl was never empty; then it was quiet. {B} held on until the hand went light, and went on holding for a while after.',
                    'Nie było cicho. {A} odkrztuszał{A?|a} to, co gorączka zrobiła z płuc, a miska nigdy nie była pusta; potem zrobiło się cicho. {B} trzymał{B?|a} za rękę, aż zrobiła się lekka, i trzymał{B?|a} jeszcze chwilę.'),

    # ------------------------------------------------------------------------------------------------ hunger, a theft, a vote
    "hung.h0": ("Bread went missing from the store", "Z magazynu zniknął chleb",
                "{B} counted the loaves twice, then a third time out loud. Nobody was looking at anyone, which in a camp this small means everyone was looking in one direction: toward {A}.",
                "{B} policzył{B?|a} bochenki dwa razy, potem trzeci raz na głos. Nikt na nikogo nie patrzył, co w tak małym obozie znaczy, że wszyscy patrzyli w jedną stronę: tam, gdzie siedział{A?|a} {A}."),
    "hung.confront": ("{B} and {A} faced each other at the storeroom door", "{B} i {A} stan{AB?ęli|ęły} naprzeciw siebie przy drzwiach magazynu",
                      "{A} did not deny it. \"It was for the little ones,\" {A} said, and that was true, and it was also a theft.",
                      "{A} się nie wypierał{A?|a}. „To było dla maluchów”, powiedział{A?|a}, i to była prawda, i to też była kradzież."),
    "hung.forgiven": ("{A} was given a place in the kitchen instead of a punishment", "{A} dostał{A?|a} miejsce w kuchni zamiast kary",
                      "{B} spoke up at the evening meeting, and the camp, tired and hungry itself, let it go. Not a crumb has gone missing since that was not handed over.",
                      "{B} zabrał{B?|a} głos na wieczornym zebraniu, a obóz, sam zmęczony i głodny, odpuścił. Od tamtej pory nie zginął ani okruch, który nie zostałby podany."),
    "hung.banish": ("The camp voted that {A} must go", "Obóz zdecydował, że {A} musi odejść",
                    "It was close. {B} voted last and did not look up. By morning the bunk was stripped, the door left open, and the road was wet.",
                    "Było blisko. {B} głosował{B?|a} jako ostatni{B?|a} i nie {B?podniósł|podniosła} wzroku. Do rana prycza została zdjęta z pościeli, drzwi zostawiono otwarte, a droga była mokra."),
    "hung.gone": ("{A} left before dawn", "{A} {A?odszedł|odeszła} przed świtem",
                  "No shouting at the gate; only a coat left folded on the bench, and the smallest piece of bread gone, as if to say: that much, and no more.",
                  "Żadnego krzyku przy bramie; tylko płaszcz złożony na ławie i najmniejszy kawałek chleba mniej, jakby to miało znaczyć: tyle i ani okruszka więcej."),
    "hung.relent": ("The vote was taken back", "Głosowanie unieważniono",
                    "It rained all night, and nobody could open the gate and look at the road. By morning {A} was at the stove, cutting onions, and nobody said a word.",
                    "Lało całą noc i nikt nie mógł otworzyć bramy i spojrzeć na drogę. Rano {A} stał{A?|a} już przy piecu i kroił{A?|a} cebulę, a nikt nie powiedział ani słowa."),

    # ------------------------------------------------------------------------------------------------ a newcomer
    "new.w0": ("{A} walked in with nothing but a knife", "{A} {A?wszedł|weszła} do obozu z niczym oprócz noża",
               "{B} took the knife, handed back the handle, and pointed at the stove. \"Sit,\" {B} said. \"We will see about the rest.\"",
               "{B} {B?wziął|wzięła} nóż, oddał{B?|a} rękojeścią i wskazał{B?|a} piec. „Siadaj”, powiedział{B?|a}. „Resztę się zobaczy.”"),
    "new.test": ("{A} got the night watch alone, and {B} pretended to sleep", "{A} dostał{A?|a} nocną wartę samotnie, a {B} udawał{B?|a}, że śpi",
                 "Every hour {B} opened one eye. By dawn the camp would know something about {A}, and something about itself.",
                 "Co godzinę {B} otwierał{B?|a} jedno oko. Do świtu obóz miał się dowiedzieć czegoś o {A} i czegoś o sobie."),
    "new.trust": ("{A} earned a bunk of {A_his} own", "{A} zasłużył{A?|a} na własną pryczę",
                  "{A} woke the camp at dawn with a pot of something hot, and nobody asked where the onions came from. {B} wrote the name on the roster in ink.",
                  "{A} obudził{A?|a} obóz o świcie garnkiem czegoś gorącego i nikt nie pytał, skąd cebula. {B} wpisał{B?|a} imię na listę atramentem."),
    "new.steals": ("{A} took a coat, a knife and the gate key", "{A} {A?wziął|wzięła} płaszcz, nóż i klucz do bramy",
                   "The lock was found open at dawn, the bowl by the stove still warm. {B} stood in the doorway a long time, saying nothing at all.",
                   "O świcie zamek znaleziono otwarty, a miska przy piecu była jeszcze ciepła. {B} długo stał{B?|a} w drzwiach i nic nie mówił{B?|a}."),
    "new.gone": ("{A} was gone before the alarm", "{A} {A?zniknął|zniknęła} przed alarmem",
                 "Whatever {A} was running from, or toward, the road took {A_him}. {B} added a line to the watch book about the lock, and under it a smaller line that said nothing about the lock.",
                 "Od czego albo do czego {A} uciekał{A?|a}, droga to pochłonęła. {B} dopisał{B?|a} w księdze warty wiersz o zamku, a pod nim mniejszy, który o zamku nic nie mówił."),
    "new.returns": ("{A} came back with the key and no explanation", "{A} wrócił{A?|a} z kluczem i bez wyjaśnień",
                    "{A} put the key on the table, took the worst bunk, the one by the door, and sat on it like a sentence. {B} nodded, once.",
                    "{A} położył{A?|a} klucz na stole, {A?wziął|wzięła} najgorszą pryczę, tę przy drzwiach, i usiadł{A?|a} na niej jak na wyroku. {B} {B?skinął|skinęła} głową, raz."),

    # ------------------------------------------------------------------------------------------------ a child and a keepsake
    "keep.k0": ("{A} hid the {keep} under the floor", "{A} schował{A?|a} {keep_acc} pod podłogą",
                "From the bigger kids, from the grown-ups, from everyone. {A} checks on it three times a day and tells nobody it is there, which is how everybody knows.",
                "Przed starszymi dziećmi, przed dorosłymi, przed wszystkimi. {A} zagląda tam trzy razy dziennie i nikomu nie mówi, że to tam jest, dzięki czemu wszyscy wiedzą."),
    "keep.found": ("{B} found the hiding place and said nothing", "{B} odkrył{B?|a} skrytkę i nic nie powiedział{B?|a}",
                   "{B} left a folded blanket beside it, in case. Some secrets want a witness more than they want safety.",
                   "{B} zostawił{B?|a} obok złożony koc, na wszelki wypadek. Niektóre sekrety bardziej potrzebują świadka niż bezpieczeństwa."),
    "keep.share": ("{A} shared the {keep} with the whole camp", "{A} podzielił{A?|a} się {keep_ins} z całym obozem",
                   "It took a whole evening, one lost piece and an argument about the rules. Nobody remembers when the common room was last this loud.",
                   "Zajęło to cały wieczór, jedną zgubioną część i kłótnię o zasady. Nikt nie pamięta, kiedy w izbie wspólnej było ostatnio tak głośno."),
    "keep.hold": ("{A} wouldn't let go of the {keep} even for a day's bread", "{A} nie oddał{A?|a} {keep_gen} nawet za cały dzień chleba",
                  "\"It's mine,\" {A} said, and it was the first time in weeks that anyone had heard {A_him} sure of something. {B} let it be.",
                  "„To moje”, powiedział{A?|a} {A} i pierwszy raz od tygodni ktoś słyszał, jak {A?jest|jest} czegoś pewn{A?y|a}. {B} dał{B?|a} spokój."),

    # ------------------------------------------------------------------------------------------------ a birth
    "birth.b0": ("{A} is expecting", "{A} jest w ciąży",
                 "{B} was the first to know, on the roof, in the one hour of the day that belongs to no one. What came out of {B_him} was not a word but a long breath.",
                 "{B?Pierwszy|Pierwsza} dowiedział{B?|a} się {B}, na dachu, w jedynej godzinie dnia, która do nikogo nie należy. Z {B?niego|niej} nie wyszło słowo, tylko długi oddech."),
    "birth.prep": ("The camp began collecting cloth for a cradle", "Obóz zaczął zbierać materiał na kołyskę",
                   "Shirts, a scarf, a flag nobody wanted to look at anymore. {B} built the frame from a broken ladder and a kind of stubborn silence.",
                   "Koszule, szalik, flaga, na którą nikt już nie chciał patrzeć. {B} zbudował{B?|a} ramę ze złamanej drabiny i upartej ciszy."),
    "birth.born": ("{A} gave birth by lamplight", "{A} urodziła przy lampie",
                   "A girl, loud and furious and perfect. The night watch changed twice and nobody went to bed. {B} named her after no one, on purpose.",
                   "Dziewczynka, głośna, wściekła i doskonała. Wartę zmieniono dwa razy i nikt nie poszedł spać. {B} nadał{B?|a} jej imię po nikim, celowo."),
    "birth.hard": ("The birth was hard, and the camp held its breath", "Poród był ciężki, a obóz wstrzymał oddech",
                   "Two hours past midnight the cry came, thin and then stronger. {A} slept for a day. The whole camp walked past the door as quietly as water.",
                   "Dwie godziny po północy rozległ się płacz, cienki, potem coraz mocniejszy. {A} spała cały dzień. Cały obóz przechodził koło drzwi cicho jak woda."),

    # ------------------------------------------------------------------------------------------------ an old one's last wish
    "wish.o0": ("{A} asked for one last thing: to {wish}", "{A} poprosił{A?|a} o jedno: {wish}",
                "It was not much to ask, and the camp took it as if it were a great deal. {A} said that if it could not be done, that was all right too.",
                "To nie było wiele, a obóz przyjął to, jakby to było bardzo dużo. {A} powiedział{A?|a}, że jeśli się nie da, to też dobrze."),
    "wish.o1": ("{B} set out to make it happen", "{B} {B?wziął|wzięła} się za spełnienie tej prośby",
                "Favours were called in, a rope was found, a thing was borrowed that had not been lent in years. It took three days and most of the camp's good humour.",
                "Przywołano przysługi, znaleziono linę, pożyczono coś, czego nie pożyczano od lat. Zajęło to trzy dni i większość dobrego humoru obozu."),
    "wish.done": ("{A} got {A_his} wish", "{A} doczekał{A?|a} się spełnienia życzenia",
                  "Wrapped in two blankets, {A} took it in without a word, then said it was nothing special, then said thank you. Nobody in camp has complained about anything since.",
                  "Owinięt{A?y|a} dwoma kocami, {A} {A?przyjął|przyjęła} to bez słowa, potem powiedział{A?|a}, że to nic specjalnego, potem podziękował{A?|a}. Odtąd nikt w obozie na nic nie narzekał."),
    "wish.after": ("{B} kept the promise after all", "{B} mimo wszystko dotrzymał{B?|a} obietnicy",
                   "{A} did not live to see it. {B} did it anyway, beside the grave, and said the wish aloud so that it would count.",
                   "{A} nie dożył{A?|a} tej chwili. {B} zrobił{B?|a} to mimo wszystko, przy grobie, i powiedział{B?|a} życzenie na głos, żeby się liczyło."),

    # ------------------------------------------------------------------------------------------------ blame after a bad match
    "blame.q0": ("{A} and {B} stopped speaking after the losses", "{A} i {B} przestali ze sobą rozmawiać po stratach",
                 "It started over who should have held the corner on {map}. By evening there were two tables, two pots and a very careful distance between them.",
                 "Zaczęło się od tego, kto miał trzymać róg na mapie {map}. Do wieczora były dwa stoły, dwa garnki i bardzo ostrożny dystans."),
    "blame.made": ("{A} and {B} shared a cup again", "{A} i {B} znowu dzielą kubek",
                   "A good day does what apologies cannot. Nobody said sorry; {B} slid the cup across, {A} drank first, and that was that.",
                   "Dobry dzień robi to, czego nie potrafią przeprosiny. Nikt nie powiedział przepraszam; {B} {B?przesunął|przesunęła} kubek, {A} napił{A?|a} się pierwsz{A?y|a} i tyle."),
    "blame.split": ("{A} asked for a different squad", "{A} poprosił{A?|a} o przeniesienie do innego oddziału",
                    "A thin day closes ranks or breaks them. {B} said nothing at the roster, and nobody could tell whether it was relief.",
                    "Chudy dzień zwiera szeregi albo je rozbija. {B} nic nie powiedział{B?|a} przy liście i nikt nie umiał ocenić, czy to ulga."),

    # ------------------------------------------------------------------------------------------------ an open gate
    "betray.t0": ("Someone opened the back gate in the night", "Ktoś otworzył tylną bramę w nocy",
                  "Nothing was taken. That is what frightened people: the gate was opened and closed again, quietly, by someone who knew the hinge.",
                  "Nic nie zginęło. Właśnie to przestraszyło ludzi: bramę otwarto i cicho zamknięto, ktoś, kto znał zawias."),
    "betray.t1": ("{B} saw {A} talking to a stranger beyond the wall", "{B} widział{B?|a}, jak {A} rozmawia z obcym za murem",
                  "The stranger wore the colours of the {enemy}, or what was left of them. {B} did not speak up until the third night; it is a very large thing to say about someone who has shared your soup.",
                  "Obcy nosił barwy {enemy_gen}, albo to, co z nich zostało. {B} odezwał{B?|a} się dopiero trzeciej nocy; to bardzo wiele powiedzieć o kimś, kto jadł z tobą jedną zupę."),
    "betray.expose": ("{A} was confronted at the gate", "{A} {A?został zagadnięty|została zagadnięta} przy bramie",
                      "{A} did not run and did not lie. \"I did not give them the camp,\" {A} said. \"I gave them the road we do not use.\" That was worse.",
                      "{A} nie uciekał{A?|a} ani nie kłamał{A?|a}. „Nie oddał{A?em|am} im obozu”, powiedział{A?|a}. „Oddał{A?em|am} im drogę, z której nie korzystamy.” To było gorsze."),
    "betray.gone": ("{A} went over to the {enemy}", "{A} {A?przeszedł|przeszła} do {enemy_gen}",
                    "The note on the pillow said only: \"Don't follow.\" {B} burned it, then regretted it, then did not.",
                    "Kartka na poduszce mówiła tylko: „Nie idźcie za mną.” {B} spalił{B?|a} ją, potem żałował{B?|a}, potem już nie."),
    "betray.pardon": ("{A} swore it was for medicine, not for them", "{A} przysięgał{A?|a}, że chodziło o leki, a nie o nich",
                      "The camp half-believed it, which in a camp is as good as a verdict. {A} stood the next four nights on the wall and was not once late.",
                      "Obóz uwierzył w połowie, a w obozie to równie dobre jak wyrok. {A} stał{A?|a} następne cztery noce na murze i ani razu się nie spóźnił{A?|a}."),
    "betray.innocent": ("{A} was only trading for medicine", "{A} tylko handlował{A?|a} za leki",
                        "A packet of bandages was put on the table. It was not enough to be an apology and too much to be a lie. {B} looked at the floor for the rest of the meeting.",
                        "Na stole położono paczkę bandaży. Za mało na przeprosiny i za dużo na kłamstwo. {B} patrzył{B?|a} w podłogę do końca zebrania."),
}

from clan_arcs_text2 import TEXT2, SPOTS            # noqa: E402  (spore, stranger, caravan, pendant, birthday)
TEXT.update(TEXT2)

# little vocabularies picked at the start of an arc: (EN, PL) ; places / tasks carry the Polish genitive
TASKS = [("supply raid", "wypadu po zapasy"), ("pharmacy run", "wyprawy do apteki"), ("scavenging run", "wyprawy po złom"), ("night patrol", "nocnego patrolu")]
PLACES = [("rail yard", "bocznicy kolejowej"), ("market square", "placu targowego"), ("flooded underpass", "zalanego tunelu"), ("burnt-out garage", "wypalonego garażu")]
WISHES = [("see the sun come up from the wall once more", "zobaczyć jeszcze raz wschód słońca z muru"), ("hear a guitar played one more time", "usłyszeć jeszcze raz gitarę"),
          ("sit by the water once more", "posiedzieć jeszcze raz nad wodą")]
# how a thing is called as KEEPSAKE inside a sentence: key -> (EN with article, PL acc, PL ins, PL gen)
KEEPS = {"chess": ("chessboard", "szachownicę", "szachownicą", "szachownicy"), "guitar": ("guitar string", "strunę gitarową", "struną gitarową", "struny gitarowej"),
         "comic": ("comic book", "komiks", "komiksem", "komiksu"), "teddy": ("teddy bear", "pluszowego misia", "pluszowym misiem", "pluszowego misia"),
         "seeds": ("pouch of seeds", "woreczek nasion", "woreczkiem nasion", "woreczka nasion"), "cards": ("deck of cards", "talię kart", "talią kart", "talii kart"),
         "harmonica": ("harmonica", "harmonijkę", "harmonijką", "harmonijki")}
# what A is to B: key -> {gender: (EN, PL nom, PL acc, PL gen)}
REL = {"sibling": {"m": ("brother", "brat", "brata", "brata"), "f": ("sister", "siostra", "siostrę", "siostry")},
       "parent": {"m": ("father", "ojciec", "ojca", "ojca"), "f": ("mother", "matka", "matkę", "matki")},
       "child": {"m": ("son", "syn", "syna", "syna"), "f": ("daughter", "córka", "córkę", "córki")},
       "mentor": {"m": ("mentor", "mentor", "mentora", "mentora"), "f": ("mentor", "mentorka", "mentorkę", "mentorki")},
       "apprentice": {"m": ("apprentice", "uczeń", "ucznia", "ucznia"), "f": ("apprentice", "uczennica", "uczennicę", "uczennicy")},
       "partner": {"m": ("partner", "partner", "partnera", "partnera"), "f": ("partner", "partnerka", "partnerkę", "partnerki")},
       "friend": {"m": ("friend", "przyjaciel", "przyjaciela", "przyjaciela"), "f": ("friend", "przyjaciółka", "przyjaciółkę", "przyjaciółki")}}
