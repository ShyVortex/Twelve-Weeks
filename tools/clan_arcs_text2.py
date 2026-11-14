"""More clan story arcs (text for tools/clan_arcs.py), EN + PL side by side; merged into clan_arcs_text.TEXT.  Same format as there:
TEXT2["<arc>.<node>"] = (headline EN, headline PL, vignette EN, vignette PL).  Extra variable: {spot} = "in the cellar of the old pharmacy" / "w piwnicy dawnej apteki"
(an in-phrase in both languages, picked per arc from SPOTS).

Arcs:  spore     canon (TLOU): breathing the spores without a mask is infection, there is no cure and no recovery.  Exposure, hiding or confessing, the signs, then the
                 end - the person turns, or asks for mercy, or walks into the dark - and the grief of the one left.  Starts only for a member who really is sick with
                 the spores (clan_story: illness "spores"); the last card removes that member from the roster.
         stranger a stranger at the gate: let in or turned away (by the clan's real supplies and morale); a gift, a cough sent on its way with a mask, an empty cup on the road
         caravan  a trade caravan camps by the road (after a real match): a trade by the clan's real supplies, or nothing to pay with; the news from the coast
         pendant  a Firefly pendant found on the way back from a real map; what it meant; worn or put away
         birthday a kid's birthday: a cake from the real stores (a can on hand) or a promise and a carved fox
"""

SPOTS = [("in the cellar of the old pharmacy", "w piwnicy dawnej apteki"), ("on the flooded subway platform", "na zalanym peronie metra"),
         ("in a sealed stairwell under the market", "w zamkniętej klatce schodowej pod targiem"), ("in the basement of a burnt-out school", "w piwnicy spalonej szkoły")]

TEXT2 = {
    # ------------------------------------------------------------------------------------------------ the spores: no cure, no way back
    "spore.sp0": ("{A} breathed the spores {spot}", "{A} wdychał{A?|a} zarodniki {spot}",
                  "The strap of the mask had snapped on the stairs, and by the time {A} noticed, the air was thick and gold in the lamplight. {A} came up coughing, laughed it off, and washed {A_his} face twice. Only {B} saw {A_his} hands shaking, and {B} knew what that meant, because everybody does: one breath of it and there is no coming back.",
                  "Pasek maski pękł jeszcze na schodach i zanim {A} to zauważył{A?|a}, powietrze w świetle lampy było gęste i złociste. {A?Wyszedł|Wyszła} na górę, kaszląc, zbył{A?|a} to śmiechem i dwa razy umył{A?|a} twarz. Tylko {B} zobaczył{B?|a}, jak {A?mu|jej} drżą ręce, i {B} wiedział{B?|a}, co to znaczy, bo wiedzą to wszyscy: jeden oddech i nie ma już powrotu."),
    "spore.hide": ("{A} said nothing and coughed into a sleeve", "{A} nic nie powiedział{A?|a} i kaszlał{A?|a} w rękaw",
                   "{A} knew that nobody comes back from it, and that nobody who has breathed it is allowed to stay, so {A} said nothing and did every chore a little too carefully. {A} took the bunk by the door. Before breakfast {B} found the grey dust on the pillow, and sat down on the floor beside it for a long time.",
                   "{A} wiedział{A?|a}, że stamtąd nikt nie wraca i że nikomu, kto to wdychał, nie pozwala się zostać, więc milczał{A?|a} i każdą robotę wykonywał{A?|a} odrobinę zbyt starannie. {A?Zajął|Zajęła} pryczę przy drzwiach. Przed śniadaniem {B} znalazł{B?|a} szary pył na poduszce i długo siedział{B?|a} obok niego na podłodze."),
    "spore.confess": ("{A} told {B} before anyone else", "{A} powiedział{A?|a} o tym najpierw {B}",
                      "\"I breathed it,\" {A} said, and then, because {B} did not move: \"I am not asking you to say it will be all right.\" There is no cure, no filter that works afterwards, no waiting it out; both of them have seen how it ends. {B} sat down next to {A}, and they stayed like that until the lamp ran dry.",
                      "„Wciągn{A?ąłem|ęłam} to”, powiedział{A?|a} {A}, a potem, bo {B} się nie poruszył{B?|a}: „Nie proszę, żebyś mówił{B?|a}, że będzie dobrze.” Nie ma lekarstwa, nie ma filtra, który pomaga po fakcie, nie ma przeczekania; oboje widzieli, jak to się kończy. {B} usiadł{B?|a} obok {A?niego|niej} i tak zostali, aż w lampie skończyła się nafta."),
    "spore.signs": ("The cough did not stop", "Kaszel nie ustawał",
                    "By the third day the whites of {A}'s eyes had gone red and the cough came up grey. {A} forgot a name, then a word, then why {A_he} had come into the room. The camp kept its distance and stayed kind, which is the cruelest way to do both. {B} did not keep {B_his} distance.",
                    "Trzeciego dnia białka oczu {A?mu|jej} poczerwieniały, a kaszel wychodził szary. {A} zapomniał{A?|a} najpierw imię, potem słowo, potem to, po co {A?wszedł|weszła} do pokoju. Obóz trzymał dystans i pozostał łagodny, co jest najokrutniejszym sposobem na jedno i drugie. {B} dystansu nie zachował{B?|a}."),
    "spore.turn": ("{A} turned in the night", "{A} przemieni{A?ł|ła} się w nocy",
                   "{A} had asked for the door to be bolted from the outside at dusk, and nobody argued. What the camp remembers is not the shot but the minute before it: the sound that was no longer a cough, and {B} saying {A}'s name once, quietly, through the wood. {B} did what {A} had asked while {A_he} could still ask.",
                   "{A} poprosił{A?|a} o zaryglowanie drzwi od zewnątrz jeszcze o zmierzchu i nikt się nie spierał. Obóz nie pamięta strzału, tylko minutę przed nim: dźwięk, który nie był już kaszlem, i to, jak {B} raz, cicho, wypowiedział{B?|a} przez drzwi imię {A}. {B} zrobił{B?|a} to, o co {A} prosił{A?|a}, dopóki jeszcze {A?mógł|mogła}."),
    "spore.mercy": ("{A} asked for it to be done while still {A_himself}", "{A} poprosił{A?|a}, by zrobić to, póki jeszcze jest sobą",
                    "At dawn {A} walked out with {B} to the {place} and said the things people say. Then {A} asked for one thing: to {wish}. They did, and afterwards {B} kept the other promise, behind the wall, with one round and both hands. The shot carried across the camp. Nobody went to look.",
                    "O świcie {A} {A?wyszedł|wyszła} z {B} do {place_gen} i powiedział{A?|a} to, co ludzie mówią w takich chwilach. Potem {A} poprosił{A?|a} o jedno: {wish}. Zrobili to, a potem {B} dotrzymał{B?|a} drugiej obietnicy, za murem, jednym nabojem i obiema rękami. Strzał poniósł się nad obozem. Nikt nie poszedł sprawdzić."),
    "spore.walk": ("{A} walked out at dusk and no one stopped {A_him}", "{A} {A?wyszedł|wyszła} o zmierzchu i nikt {A?go|jej} nie zatrzymał",
                   "{A} left the mask on its hook, the coat on its nail and the gate unlatched behind {A_him}. \"Don't follow,\" {A} said, \"and don't open it again tonight.\" The watch kept it shut. Before leaving {A} had sat by the fire for an hour and asked everyone to talk about anything but this. A day's walk, perhaps, before it takes hold; after that nobody knows, and nobody writes it down.",
                   "{A} zostawi{A?ł|ła} maskę na haku, płaszcz na gwoździu, a bramę niezaryglowaną. „Nie idźcie za mną”, powiedział{A?|a}, „i nie otwierajcie jej więcej tej nocy.” Warta trzymała ją zamkniętą. Przed odejściem {A} godzinę siedział{A?|a} przy ogniu i prosił{A?|a}, żeby wszyscy mówili o czymkolwiek, byle nie o tym. Dzień drogi, może, zanim to się zacznie; potem nikt nie wie i nikt tego nie zapisuje."),
    "spore.remembered": ("{A}'s bunk was stripped before noon", "Prycza po {A} została zdjęta z pościeli jeszcze przed południem",
                         "It went the way everyone had known it would, and sooner than anyone had braced for. {B} took the mask from the hook and could not decide whether to bury it or keep it, so it still hangs there.",
                         "Skończyło się tak, jak wszyscy wiedzieli, że się skończy, i szybciej, niż ktokolwiek się spodziewał. {B} {B?zdjął|zdjęła} maskę z haka i nie potrafił{B?|a} zdecydować, czy ją pochować, czy zatrzymać, więc wisi tam do dziś."),
    "spore.after": ("{B} did not speak at supper", "{B} nie odezwał{B?|a} się przy kolacji",
                    "The camp aired every room and boiled every cloth, as if that would have helped. It would not have; that is not why they did it. A second bowl was set out by habit and quietly taken away. A kid asked why nobody said {A}'s name, and {B} answered: \"We will. Not yet.\"",
                    "Obóz wywietrzył każdą izbę i wygotował każdą szmatę, jakby to miało coś dać. Nie miało; nie dlatego to robili. Druga miska została postawiona z przyzwyczajenia i cicho zabrana. Jakieś dziecko zapytało, czemu nikt nie mówi imienia {A}, a {B} odpowiedział{B?|a}: „Powiemy. Jeszcze nie.”"),

    # ------------------------------------------------------------------------------------------------ a stranger at the gate
    "stranger.st0": ("A stranger stood at the gate at dusk", "O zmierzchu pod bramą stanął obcy",
                     "No pack, no weapon, a scarf pulled up over the mouth against the dust. {A} spoke to the stranger through the bars while {B} counted the shadows on the road behind and found none. \"Only a roof,\" the stranger said. \"Until the weather turns.\"",
                     "Bez plecaka, bez broni, z szalikiem naciągniętym na usta przed pyłem. {A} rozmawiał{A?|a} z obcym przez kraty, a {B} liczył{B?|a} cienie na drodze za jego plecami i nie znalazł{B?|a} żadnego. „Tylko dach”, powiedział obcy. „Dopóki nie zmieni się pogoda.”"),
    "stranger.in": ("The gate was opened", "Brama została otwarta",
                    "It was {A}'s call, and {A} made it with the lamp held high so that everyone could see the face. The stranger ate standing up, as if sitting would have to be paid for, and told about the road: which bridges are down, which wells are good. By midnight half the camp was listening and the other half was pretending not to.",
                    "Decyzja należała do {A}. {A?Podjął|Podjęła} ją z lampą uniesioną wysoko, żeby wszyscy widzieli tę twarz. Obcy jadł na stojąco, jakby za siedzenie trzeba było płacić, i opowiadał o drodze: które mosty leżą, które studnie są dobre. O północy połowa obozu słuchała, a druga połowa udawała, że nie."),
    "stranger.out": ("The gate stayed shut", "Brama pozostała zamknięta",
                     "{B} wanted to open it. {A} did not, and the camp, thin on bread as it was, did not overrule {A_him}. A tin of soup and a canteen went out through the bars. The stranger said thank you three times, politely, and did not look back at the wall.",
                     "{B} chciał{B?|a} ją otworzyć. {A} nie chciał{A?|a}, a obóz, ubogi w chleb, nie sprzeciwił się {A?jemu|jej}. Przez kraty wyszła puszka zupy i manierka. Obcy podziękował trzy razy, grzecznie, i nie obejrzał się na mur."),
    "stranger.gift": ("The stranger left at dawn and left a map behind", "Obcy odszedł o świcie i zostawił mapę",
                      "Drawn in pencil on the back of a ration label: the good wells, a cellar full of tinned fish, a road to avoid. {B} pinned it above the table. It was not a payment, the stranger had said. It was just what you do when somebody leaves a lamp on.",
                      "Narysowana ołówkiem na odwrocie etykiety z racji: dobre studnie, piwnica pełna ryb w puszkach, droga, której należy unikać. {B} {B?przypiął|przypięła} ją nad stołem. To nie była zapłata, powiedział obcy. Tak się po prostu robi, gdy ktoś zostawia zapaloną lampę."),
    "stranger.cough": ("The stranger coughed in the night", "Obcy zakaszlał w nocy",
                       "Only a dry cough, a cold most likely, but nobody sleeps easy in a house with a cough. At dawn {A} and {B} walked the stranger to the gate with a day of water and a spare filter mask from the shelf. Nobody was cruel about it, and the stranger asked for nothing more, which is the part {A} keeps thinking about.",
                       "Zwykły suchy kaszel, najpewniej przeziębienie, ale w domu, w którym ktoś kaszle, nikt nie śpi spokojnie. O świcie {A} i {B} odprowadzi{AB?li|ły} obcego do bramy z zapasem wody na dzień i zapasową maską z filtrem z półki. Nikt nie był okrutny, a obcy o nic więcej nie prosił, i właśnie o tym {A} wciąż myśli."),
    "stranger.echo": ("A tin cup was found on the road", "Na drodze znaleziono blaszany kubek",
                      "Three days after the gate stayed shut, the watch brought in a tin cup from the roadside, clean, set upside down on a stone, the way you set down a thing you mean to come back for. It settled nothing. {A} hung it on a nail by the gate and nobody has had the heart to ask why.",
                      "Trzy dni po tym, jak brama została zamknięta, wartownicy przynieśli z pobocza blaszany kubek, czysty, odwrócony na kamieniu, tak jak kładzie się rzecz, po którą zamierza się wrócić. Niczego to nie rozstrzygnęło. {A} powiesi{A?ł|ła} go na gwoździu przy bramie i nikt nie ma serca zapytać po co."),

    # ------------------------------------------------------------------------------------------------ a trade caravan
    "caravan.car0": ("A trade caravan camped by the road", "Przy drodze rozbiła się karawana handlarzy",
                     "Four wagons, two mules and a hand-painted sign: honest weights. {A} went out to look at the goods and came back with a list; {B} went out to look at the people and came back saying nothing at all. The traders keep to the road, and in these years the road is neutral ground only for as long as everybody remembers to be polite.",
                     "Cztery wozy, dwa muły i ręcznie malowany szyld: uczciwe wagi. {A} {A?poszedł|poszła} obejrzeć towar i wrócił{A?|a} z listą; {B} {B?poszedł|poszła} obejrzeć ludzi i wrócił{B?|a}, nie mówiąc nic. Handlarze trzymają się drogi, a w tych latach droga jest ziemią niczyją tylko dopóki wszyscy pamiętają o grzeczności."),
    "caravan.trade": ("{A} struck a bargain with the traders", "{A} ubi{A?ł|ła} interes z handlarzami",
                      "It came down to a fair swap in the end: a sack of what the last raid brought home against two bandages and a bottle of something clear. {A} haggled as if the fate of the camp depended on it, and in a small way it did. The traders shook hands on it and counted twice.",
                      "Skończyło się uczciwą wymianą: worek tego, co przyniósł ostatni wypad, za dwa bandaże i butelkę czegoś przezroczystego. {A} targował{A?|a} się, jakby od tego zależał los obozu, i w pewnym małym sensie zależał. Handlarze uścisnęli sobie dłonie na zgodę i policzyli dwa razy."),
    "caravan.poor": ("The caravan had nothing we could pay for", "U karawany nie było nic, na co nas było stać",
                     "The camp's hands were too empty to buy anything. {A} bought one thing only, a spool of thread, with {A_his} own ration of coffee, and {B} pretended not to see the price. The wagons rolled on at first light, and the road felt longer for a day after.",
                     "Obozowi brakowało czym płacić. {A} kupił{A?|a} tylko jedną rzecz, szpulę nici, za własną rację kawy, a {B} udawał{B?|a}, że nie widzi ceny. Wozy ruszyły o pierwszym świcie, a droga przez dzień po tym wydawała się dłuższa."),
    "caravan.news": ("The traders had news from the coast", "Handlarze przywieźli wieści znad morza",
                     "They had come through the outer districts of Seattle and down to the water: {enemies} have moved their patrols, the ferry is running again for a price, and the sea road stays open until the first frost. {B} wrote it all down on the back of a map, and {A} kept the one useful sentence.",
                     "Przeszli przez zewnętrzne dzielnice Seattle aż do wody: {enemy} przesunęły swoje patrole, prom znów pływa za odpowiednią cenę, a morska droga jest otwarta do pierwszych mrozów. {B} {B?spisał|spisała} wszystko na odwrocie mapy, a {A} {A?zapamiętał|zapamiętała} to jedno użyteczne zdanie."),

    # ------------------------------------------------------------------------------------------------ a Firefly pendant
    "pendant.fp0": ("{A} found a Firefly pendant", "{A} znalaz{A?ł|ła} wisiorek Świetlików",
                    "Dented, on a cord gone brittle, a firefly stamped into the tin. {A} picked it up on the way back from the place they call {map}, from under a rotted table in a room nobody had touched in twenty years. {A} did not know what it was. {B} went very quiet when {A} held it out.",
                    "Wgnieciony, na sznurku, który zrobił się kruchy, z wybitym w blasze świetlikiem. {A} {A?podniósł|podniosła} go w drodze powrotnej z miejsca zwanego {map}, spod przegniłego stołu w pokoju, którego nikt nie dotykał od dwudziestu lat. {A} nie wiedział{A?|a}, co to jest. {B} zamilkł{B?|a} zupełnie, gdy {A} {A?wyciągnął|wyciągnęła} go przed siebie."),
    "pendant.tell": ("{B} knew what it meant", "{B} wiedział{B?|a}, co ten wisiorek znaczy",
                     "Long ago, before the quarantine zones shrank to what they are now, the Fireflies stood for a cure, and plenty of people believed in the dream long after the dream was shot. {B} said it quietly, turning the pendant in the lamplight, and for once did not make a story of it. Whatever it was, it had belonged to somebody who believed in something.",
                     "Dawno temu, zanim strefy kwarantanny skurczyły się do tego, czym są teraz, Świetliki znaczyły lekarstwo, a wielu ludzi wierzyło w to marzenie długo po tym, jak je rozstrzelano. {B} powiedział{B?|a} to cicho, obracając wisiorek w świetle lampy, i tym razem nie zrobił{B?|a} z tego opowieści. Cokolwiek to było, należało do kogoś, kto w coś wierzył."),
    "pendant.worn": ("{A} wears it now", "{A} nosi go teraz",
                     "Under the shirt, against the skin, where nobody can see it and everybody knows. The kids ask what the firefly is. {A} says it is a kind of light that doesn't go out, and that this is, technically, a lie, and also not.",
                     "Pod koszulą, na skórze, gdzie nikt go nie widzi, a wszyscy wiedzą. Dzieci pytają, czym jest świetlik. {A} odpowiada, że to taki rodzaj światła, które nie gaśnie, że technicznie jest to kłamstwo, a jednak nie do końca."),
    "pendant.tin": ("The pendant went into a tin", "Wisiorek trafił do puszki",
                    "{A} put it in an old tobacco tin with the other things that have no use any more: a button, a key to nothing, a photograph with the faces rubbed off. Not hidden. Just kept. Some things want to be remembered rather than worn.",
                    "{A} schowa{A?ł|ła} go do starej puszki po tytoniu razem z innymi rzeczami, które już do niczego nie służą: guzikiem, kluczem do niczego, zdjęciem ze zniszczonymi twarzami. Nie ukryty. Po prostu zachowany. Niektóre rzeczy chcą być pamiętane, a nie noszone."),

    # ------------------------------------------------------------------------------------------------ a kid's birthday
    "birthday.bd0": ("It was {A}'s birthday, or near enough", "{A} miał{A?|a} urodziny, albo prawie",
                     "Nobody keeps a calendar any more, but {B} keeps the week, and the week came round. {A} pretended not to know and failed, loudly, and a whole morning went by with nobody asking about the thing in {B}'s pocket.",
                     "Nikt już nie prowadzi kalendarza, ale {B} pilnuje tygodnia, a tydzień wrócił. {A} udawał{A?|a}, że nie wie, i nie udało się to ani trochę, a przez cały ranek nikt nie pytał o to, co {B} ma w kieszeni."),
    "birthday.cake": ("There was cake, more or less", "Był tort, mniej więcej",
                      "Somebody found {thing}, opened it with the good can opener, spooned it onto a flat biscuit and stuck a single stub of candle in the middle. {A} blew it out too soon and had to start again. Everyone got one forkful and {A} got the middle, and said it was the best thing {A_he} had ever eaten, and it probably was.",
                      "Ktoś znalazł {thing}, otworzył ją dobrym otwieraczem, nałożył na płaski sucharek i wbił w sam środek jeden ogarek świecy. {A} {A?zdmuchnął|zdmuchnęła} go za wcześnie i musiał{A?|a} zaczynać od nowa. Każdy dostał po jednym widelcu, a {A} środek, i powiedzia{A?ł|ła}, że to najlepsza rzecz, jaką jadł{A?|a}, i pewnie tak było."),
    "birthday.promise": ("No cake this year, only a promise", "W tym roku bez tortu, za to z obietnicą",
                         "The shelves would not stretch. {B} knelt, looked {A} in the eye and promised: next year, a real one, with layers. {A} considered this seriously and said that layers were a big ask, but {A_he} would accept the offer, and shook {B}'s hand.",
                         "Półki nie mogły się rozciągnąć. {B} {B?uklęknął|uklęknęła}, spojrzał{B?|a} {A} w oczy i obiecał{B?|a}: za rok prawdziwy, z warstwami. {A} rozważył{A?|a} to poważnie i powiedział{A?|a}, że warstwy to duże wymaganie, ale przyjmie propozycję, i {A?uścisnął|uścisnęła} dłoń {B}."),
    "birthday.kept": ("A small wooden fox, whittled by lamplight", "Mała drewniana lisia figurka, wystrugana przy lampie",
                      "It wasn't a cake. It had four legs and one ear slightly longer than the other, and {B} had been working on it every night since. {A} said nothing, took it in both hands, and slept with it on the pillow like a person who has been given something that cannot be spoiled.",
                      "To nie był tort. Miała cztery łapy i jedno ucho odrobinę dłuższe od drugiego, a {B} pracował{B?|a} nad nią co noc od tamtej pory. {A} nic nie powiedział{A?|a}, {A?wziął|wzięła} ją w obie dłonie i {A?zasnął|zasnęła} z nią na poduszce jak ktoś, komu dano coś, czego nie da się zepsuć."),
}
