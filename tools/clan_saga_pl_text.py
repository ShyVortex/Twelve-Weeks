"""Polish clan saga templates, part 1: line for line parallel to clan_saga_text.py (same pools, same order, same W: / S: scopes).  See clan_saga_pl.py for the rules."""
TEXT = r"""
== loss.title
{A} czekał{A?|a} przy bramie i o nic nie pytał{A?|a}
Nikt nie śpiewał po {map_loc}
{map_at} {enemies} nie ustąpiły, a my zapłaciliśmy
Przegraliśmy {map_acc}
Cicha kolacja po {map_loc}
Zły wieczór {map_at}
{A} dwa razy przeliczył{A?|a} karabiny
== loss.event
{map_at} górę wzięły {enemies}. Wycofano się {place_from}, na tablicy {k_dn} po ich stronie, za mało, żeby cokolwiek znaczyło, a w ubraniu został {smell}.
Kiedy {map_at} pękła linia, cofnięto się {place2_from}, mając za plecami {enemies}, a przed sobą zamknięte drzwi. Ustąpiły dopiero po trzecim kopniaku.
Przegraliśmy {map_acc}. Po ich stronie naliczono {k_dn}. Ostatni opór stawiono {place_at}, a ostatnie, co było widać, to podłoga lecąca w twarz.
{map_at} nie było litości. {place_at} stali najlepsi z {enemies_gen}, a kiedy natarcie dotarło {place2_to}, nie zostało z niego nic, o czym warto mówić.
Wychodziło się {map_from} tyłem, z pięścią zaciśniętą na czyimś pasie, a {enemies} wiwatowały {place_at}, i własny oddech rzęził jak piła.
Porażka {map_at}: {k_dn}, długi powrót na czworakach {place2_ins} i cisza tam, gdzie powinny paść ostatnie rozkazy.
== loss.camp
{A} siedział{A?|a} przy piecu i obierał{A?|a} ziemniaka w jedną długą wstęgę, raz po raz, i nie zjadł{A?|a} z niego ani kawałka.
{A} zmył{A?|a} ci krew z rąk w misce; woda poszarzała, potem zrobiła się zimna.
{A} dwa razy przeliczył{A?|a} karabiny na stojaku i za każdym razem były wszystkie, co tylko pogarszało sprawę.
Ktoś wyłączył radio i nikt go już nie włączył.
Dzieci wysłano wcześnie do łóżek i leżały z uchem przyłożonym do ściany.
{A} {A?warknął|warknęła} na {B} o łyżkę, a potem przeprosił{A?|a} całą kromką chleba.
== loss.b
{B} powiedział{B?|a}, że to wina {place2_gen}, bo zawsze winna jest ziemia, a nigdy nogi.
{B} chciał{B?|a} wyjść jeszcze tej nocy i trzy różne osoby powiedziały nie.
{B} {B?wziął|wzięła} pierwszą wartę i nie dał{B?|a} się zluzować.
{B} nie powiedział{B?|a} nic, co było dość głośne.
{B} czyścił{B?|a} ten sam karabin, aż zamek zalśnił, a potem czyścił{B?|a} go jeszcze raz.
== loss.streak
To już {lossw} z rzędu, a tablicy przy drzwiach nikt już nie prowadzi.
To dwie porażki z rzędu i stołówka to zauważyła.
Po {prev_map_loc} {map}. Ludzie liczą i nie podoba im się suma.
== loss.recover
Wczoraj też poszło źle {prev_map_at}; {A} {A?mruknął|mruknęła}, że pech to tylko nawyk, którego nikt jeszcze nie przełamał.
== down.title
{A} zszył{A?|a} ci {site_acc} {camp_at}
Powalono cię {dn_p}, a {A} liczy siniaki
{A} wybierał{A?|a} szkło z twoich ran
{A} nie pozwolił{A?|a} ci spać, dopóki nie przestały drżeć ręce
{A} prowadził{A?|a} rachunek na twoich żebrach
== down.event
Powalono cię {dn_p} {map_at}, ostatni raz twarzą w dół {place_at}, z {enemies_ins} stojącymi nad tobą i z {wpn_ins} poza zasięgiem ręki.
Kładziono cię na ziemię {dn_p} {map_at}: raz doczołgano się o własnych siłach, raz wywleczono cię za kołnierz {place_from}, raz po prostu leżało się.
{map_at} powalono cię {dn_p}. Ostatnie powalenie zostawiło tylko sufit {place_gen} nad głową i serce, które robiło się miękkie.
Lądowało się {dn_p} na podłodze {place_gen}, {map_at}, a za każdym razem czyjeś ręce znajdowały cię wcześniej niż {enemies}.
Na dół {place_at}, na nogi, znów na dół {place2_at}: {dn_p} {map_at}, zanim się skończyło.
Kamizelka wzięła na siebie, ile mogła, a kiedy już nie mogła, powalono cię {dn_p}, {place_at}, a potem {place2_at}.
== down.care
{A} {A?odciął|odcięła} rękaw, przepłukał{A?|a} ranę z czajnika, który był za gorący, i zszył{A?|a} ją żyłką, jedenaście szwów, ciasnych i brzydkich.
{A} trzymał{A?|a} lampę nisko, a w drugiej ręce pęsetę, i {A?wyciągnął|wyciągnęła} ci {site_from} odłamek szkła, który wszedł pod skórę i szedł dalej.
{A} {A?wcisnął|wcisnęła} dwa palce w siniak na twoich żebrach, aż zaklęto, po czym {A?kiwnął|kiwnęła} głową i powiedział{A?|a}, że nic nie jest złamane, tylko obrażone.
{A} {A?owinął|owinęła} ci {site_acc} {cloth_ins} i zawiązał{A?|a} węzeł dwa razy, tak jak teraz wiąże wszystko.
{A} odlepiał{A?|a} koszulę od zaschniętej krwi po trochu, ciepłą wodą, i cały czas mówił{A?|a} o niczym, żeby bolało mniej.
{A} zszył{A?|a} rozcięcie i powiedział{A?|a} dzieciom, że wpadło się na drzwi.
== down.after
Nikt nie pytał, jak poszło. Patrzyli na szwy i wracali do zupy.
Dzieci ustawiły się w kolejce, żeby dotknąć siniaka, i usłyszały, że można patrzeć, ale nie dźgać.
{B} {B?przyniósł|przyniosła} blaszany kubek czegoś ciepłego i zostawił{B?|a} go przy twojej ręce.
{B} {B?ściągnął|ściągnęła} ci buty i ustawił{B?|a} je przy drzwiach, żeby się znalazły.
{B} powiedział{B?|a}, że wygląda to gorzej, niż jest, co mówi się każdemu, kto tak wygląda.
{A} mówi, że ta blizna będzie ci do twarzy.
== down.you
Twój szew {ysite_at}, założony po {ymap_loc} w dniu {yd}, był pierwszym, na co {A} spojrzał{A?|a}. Wytrzymał.
Cięcie po {ymap_loc} (dzień {yd}) rozeszło się znów na szerokość kciuka, a {A} powiedział{A?|a}, co o tym sądzi, i to długo.
== win.title
Zajęliśmy {map_acc}, a {A} nie ukrywa uśmiechu
Utrzymaliśmy {map_acc}
{A} walił{A?|a} łyżką w garnek na cześć {map_gen}
Dobry wieczór {map_at}
{map_at} było nasze przed zmrokiem
{A} postawił{A?|a} czajnik, zanim doszło się do bramy
== win.event
{map_at} wygrano: {k_dn}, a ostatnie z {enemies_gen} opuściły {place_acc} o zmierzchu ze słońcem w oczach.
Trzymano {place_acc}, {map_at} przeciw {enemies_dat}, aż przestały nacierać; pod koniec na ziemi leżało {k_dn}, a uszy dzwoniły jak dzwon.
Wygrana {map_at}. Po ich stronie {k_dn}, a wyszło się przez {place2_acc} jak ktoś, kto ma dokąd iść.
Zajmowano {map_acc} pomieszczenie po pomieszczeniu: najpierw {place_acc}, potem {place2_acc}, a gdy ucichło, słychać było wodę kapiącą na coś, co nie było metalem.
{enemies} runęły przez {place_acc}, {map_at}, a tam już ktoś stał; po wszystkim {k_dn}, przebieg, którego nie dało się zaplanować.
Po raz ostatni tego dnia wyparto {enemies} {place_from}, {map_at}, razem {k_dn}, i przez minutę siedziano na schodach, a wokół był {air}.
== win.camp
{A} powiesił{A?|a} twoją kurtkę przy piecu i udawał{A?|a}, że nie patrzy na dziury w niej.
Dzieci odegrały całą sprawę na podwórku kijami, a {enemies} za każdym razem przegrywały.
{A} odkroił{A?|a} ci piętkę chleba, kawałek, którego chce każdy.
Ktoś znalazł ogarek świecy i zapalił go, bez powodu, który ktokolwiek podał.
{A} powiedział{A?|a} to na głos: jeszcze jeden dzień, w którym nikt nie musi kopać.
Nawet {A}, {A?który|która} tego nie robi, zaśmiał{A?|a} się z czegoś, co powiedział{B?|a} {B}, i nie umiał{A?|a} powiedzieć, z czego.
== win.hs
{hs_nom} wśród nich, a {A} chce usłyszeć tę część jeszcze raz, powoli.
{hs_nom}, a {A} powtarza tę liczbę jak modlitwę.
== win.after_loss
Po {prev_map_loc} wczoraj {A} nie śmiał{A?|a} uwierzyć i kazał{A?|a} ci to powtórzyć dwa razy.
Po {prev_map_loc} to było jak zimna woda na oparzenie.
== win.big
{A} zawiązał{A?|a} kolejny węzeł na sznurku nad drzwiami, jeden na każdy dobry dzień, a tych węzłów jest więcej, niż ktokolwiek się spodziewał.
== exec.title
{ex_nom} {map_at}, a {A} unika twojego wzroku
{A} zapytał{A?|a}, jak było {map_at}, i nic nie odpowiedziano
Co zrobiono {place_at}
{A} godzinę szorował{A?|a} twój rękaw w zimnej wodzie
== exec.event
Skończono {ex_acc} na podłodze {place_gen}, {map_at}, z bliska, nożem, i dźwięk był bardziej mokry, niż pamiętano.
{ex_nom} {map_at}. Jeden z nich spojrzał na ciebie {place_at} i splunął, a i tak to zrobiono.
{map_at} zrobiono to powoli: kolano w plecy, dłoń na usta, a podłoga {place_gen} poczerwieniała aż do listew.
Trzy sekundy na każdego, nie więcej, razem {ex_nom}, {place2_at}, {map_at}. Nigdy nie trwa to tak krótko, jak się mówi.
Rozcięto gardło {place_at}, {map_at} i trzymano, aż skończy, a potem następne, {ex_nom}, zanim minął wieczór, a {smell} zmienił się w miedź.
== exec.react
{A} {A?wziął|wzięła} twój rękaw, namoczył{A?|a} go w zimnej wodzie i szorował{A?|a} ciemne, sztywne plamy szczotką, aż pękła skóra na kostkach {A?jego|jej} palców.
{B} {B?przesunął|przesunęła} się na ławce o szerokość dłoni, potem zawstydził{B?|a} się i {B?przesunął|przesunęła} z powrotem.
Dzieci usłyszały i zapytały, a {A} powiedział{A?|a}, że to rzecz, którą robią dorośli, żeby dzieci mogły zachować zabawki, i nikogo to nie zadowoliło.
{A} powiedział{A?|a}: tak to jest, płaskim głosem, i {A?wyszedł|wyszła} na długo na zewnątrz.
Przy kolacji nikt nie komentował. Chochla skrobała o dno garnka.
== rev.title
Wyniesiono {rv_acc} {map_from}
{A} liczy tych, których podniesiono
{A} chce wiedzieć, do ilu rąk się dotarło
== rev.event
{map_at} postawiono na nogi {rv_acc}, raz pod ostrzałem {place_at}, kiedy kule zdzierały tynk ze ściany nad głowami.
{map_at} podniesiono {rv_acc} i czołgano się ostatnie trzy metry {place2_to} na łokciach, żeby dotrzeć do trzeciego, z ustami pełnymi pyłu.
{map_at} zerwano z ziemi {rv_acc}. Jeden krwawił przez palce i podziękował trzy razy, nie słysząc siebie.
== rev.react
{A} zapisał{A?|a} to, nie zabitych, tylko podniesionych. To inna kolumna i {A} mówi, że ta się liczy.
{A} zawiązał{A?|a} węzeł na sznurku za każdego, kogo podniesiono, i zawiesił{A?|a} sznurek nad twoją pryczą.
{B} powiedział{B?|a}, że mogło się zostać za osłoną, i w tym samym oddechu podziękował{B?|a}, żeby nie dało się spierać.
== quiet.title
{map_at}: jak zwykle, a zwykle wystarcza
Nic godnego uwagi {map_at}
Zwykły dzień {map_at}
{A} zapytał{A?|a} o {map_acc}, a w odpowiedzi wzruszono ramionami
== quiet.event
Wieczór {map_at}: {k_dn}, nic ładnego i nic, o czym warto opowiadać, tylko {place} i długi powrót obok {place2_gen}.
{map_at} nic się nie złamało. {k_dn}, długie czekanie {place_at} i {air}.
{map_at} było {k_dn} i popołudnie pełne {air_gen}; wrócono z mokrymi butami i pustą głową.
Powrót {map_from} przed lampami: {k_dn}, zimna dłoń, uczciwy dzień roboty.
== quiet.camp
{A} nie naciskał{A?|a} na szczegóły i podał{A?|a} ci miskę.
{camp_at} pachniało gotowaną cebulą i mokrą wełną.
Ktoś naprawił ci pasek, kiedy cię nie było.
{A} pokazał{A?|a} rysunek dzieci, na którym masz za dużo rąk.
== bridge.same_map
To znowu {map}, {nth} w tym tygodniu, a {A} zna już {place_acc} na pamięć, po pęknięciach.
Znowu {map}. {A} powiedział{A?|a}, że ziemia musi mieć już dość widoku twoich butów.
== bridge.you_scar
Twój szew {ysite_at}, założony po {ymap_loc} w dniu {yd}, zrósł się w różową kreskę.
== hurt.line
{B} wrócił{B?|a} {map_from} z raną na {site_loc} otwartą przez {cause_acc}, do białej kości, i usiadł{B?|a} bardzo ostrożnie na najbliższej skrzynce.
{B} {B?wszedł|weszła} kulejąc za tobą, z raną na {site_loc} zniszczoną przez {cause_acc} {place2_at}, i nie dał{B?|a} się nieść.
{B} oberwał{B?|a} {cause_ins} w {site_acc} {place2_at}; {A} {A?rozciął|rozcięła} rękaw i zamilkł{A?|a} na widok tego, co było pod spodem.
== mark.line
{A} {A?owinął|owinęła} {B?jego|jej} {site_acc} {cloth_ins} i powiedział{A?|a}, że minie kilka dni, zanim {B} będzie {B?mógł|mogła} {job}.
== haul.title
{A} wysypał{A?|a} worek {map_from} na podłogę
Co przyniesiono {map_from}
{A} dwa razy przeliczył{A?|a} łup {map_from}
Inwentarz po {map_loc}
{A} spisał{A?|a} to, co wróciło {place_from}
{A} ułożył{A?|a} łup {map_from} w rzędy
== haul.found
Worek {place_from} oddał {loot_list}.
{place2_from}, zawinięte w czyjąś starą koszulę, przyniesiono {loot_list}.
{map_from} przyniesiono {loot_list}, większość {place_from}.
Przyniesiono {loot_list}, mówił rachunek, wszystko {place_from}.
== haul.food
Puszki były powgniatane i bez etykiet; {A} {A?potrząsnął|potrząsnęła} jedną koło ucha, {A?uśmiechnął|uśmiechnęła} się i napisał{A?|a} na wieczku smalcem optymistyczną wróżbę.
{A} powąchał{A?|a} otwartą puszkę tak, jak inni czytają list.
Jedzenie idzie prosto do garnka, a {A} już zdecydował{A?|a}, kto dostanie pierwszą chochlę.
== haul.med
{A} posortował{A?|a} lekarstwa według tego, jak bardzo powinny nas przerażać; antybiotyki poszły do skrzynki na klucz, reszta do szafki.
{A} ułożył{A?|a} opatrunki w rząd i liczył{A?|a} na głos, jakby powtarzanie mogło ich przybyć.
== haul.ammo
{A} wsypywał{A?|a} naboje do puszki po kawie jeden po jednym, a dźwięk był niemal przyjemny.
{A} podzielił{A?|a} naboje na papierowe zwitki po pięć i na każdym napisał{A?|a} ołówkiem liczbę.
== haul.tool
{A} {A?uniósł|uniosła} znalezisko do lampy i pierwszy raz w tym tygodniu {A?uśmiechnął|uśmiechnęła} się.
{A} obracał{A?|a} narzędzie w rękach, mówiąc cicho i czule, do czego służy.
== haul.keep
{B} zgłosił{B?|a} prawo do {kitem_a_gen} dla dzieci, zanim worek zdążono zamknąć.
{A} położył{A?|a} {kitem_a_acc} na półce nad piecem, gdzie każdy może zobaczyć i nikt nie może udawać, że tego nie widzi.
== use.title
{A} zużył{A?|a} część {item_pl_gen} {kmap_from}
Pamiętasz {item_short} {kplace_from}?
{A} otworzył{A?|a} to, co przyniesiono do domu w dniu {kd}
== use.ammo
{A} zużył{A?|a} {n} z {item_pl_gen} {kmap_from} (znalezionych {kd_ago}) na strzelanie do celu za murem i każdy strzał był lekcją.
{A} przeliczył{A?|a} to, co zostało z {item_pl_gen} {kplace_from}: {n_left}. Nie starczy na miesiąc i {A} powiedział{A?|a} to na głos.
== use.food
{A} ugotował{A?|a} {item_pl} {kplace_from} na wieczorny posiłek i odmówił{A?|a} modlitwę, o którą nikt nie prosił.
{A} otworzył{A?|a} ostatnie {item_pl} {kmap_from}, odłożone od dnia {kd}, i podzielił{A?|a} je z dziećmi łyżka po łyżce.
== use.med
{A} zużył{A?|a} jedną sztukę z {item_pl_gen} {kplace_from} i zapisał{A?|a} to w rejestrze małą, żałosną kreską.
{A} otworzył{A?|a} ostatnie z {item_pl_gen} {kmap_from} na gorączkę, która nie chciała spaść.
== use.tool
{A} użył{A?|a} jednego z {item_pl_gen} {kplace_from} (dzień {kd}), żeby naprawić to, co było zepsute od wiosny, i {A?poszedł|poszła} szukać następnej rzeczy.
{A} był{A?|a} dumn{A?y|a} z {item_pl_gen} {kmap_from} i pokazywał{A?|a} je każdemu, kto usiedział spokojnie.
== keepcb.title
{kitem} {kmap_from} znów się pojawia
{A} i {kitem}
{kitem} z dnia {kd} nadal w użyciu
== keepcb.chess
Na szachownicy {kplace_from} (dzień {kd}) rozgrywa się już turniej. {A}, {A?który|która} był{A?|a} zbyt dumn{A?y|a}, żeby poznać zasady, przegrał{A?|a} z sześciolatkiem i {A?przyjął|przyjęła} to z godnością.
{A} znalazł{A?|a} zaginionego czarnego skoczka w kurzu pod piecem i {A?wsunął|wsunęła} go z powrotem na szachownicę {kmap_from} bez słowa.
== keepcb.guitar
{A} nauczył{A?|a} się trzech nut na strunie {kplace_from}, brzmią jak drzwi; dzieci nucą je do siebie z pokoju do pokoju.
== keepcb.comic
Komiks {kplace_from} jest czytany po raz czterdziesty; {A} robi głosy, a dzieci są już za duże, żeby dać się nabrać, ale przychodzą posłuchać.
== keepcb.teddy
Miś {kmap_from} trafił do {B}, {B?który|która} zaprzecza, że to ją obchodzi, i śpi z ręką na jego uchu.
== keepcb.seeds
{A} zasadził{A?|a} nasiona {kplace_from} w pudełku po butach na parapecie, sprawdza je dwa razy dziennie i mówi, że wszystko w porządku. Nic jeszcze nie wzeszło.
== keepcb.cards
Grają teraz talią {kplace_from}, bez siódemki trefl, którą {A} zastąpił{A?|a} nową, wyciętą z pudełka po racjach, i nigdy nie dał{A?|a} się przyłapać.
== keepcb.harmonica
Harmonijka {kplace_from} wędruje po {camp_loc} z rąk do rąk; {A} jest jedynym, kto potrafi wydobyć z niej prawdziwą melodię, i tylko gdy nikt nie patrzy.
== inj.title
{A} nadal oszczędza {site_acc}
{A}: rana na {site_loc} nie zapomniała o {kmap_loc}
Jak się ma {A}
{A} nie przyzna, że nadal boli
== inj.fresh
{A} wrócił{A?|a} {kmap_from} w dniu {kd} z raną na {site_loc}, owiniętą {cloth_ins}; twierdzi, że to nic, i nie obciąża jej.
== inj.mid
{A?Jego|Jej} rana na {site_loc} jest nadal owinięta, opatrunek poszarzał, a {A} robi jedną ręką rzeczy na jedną rękę i przeklina te na dwie.
{A} nie może {job_neg} z kontuzją {site_gen}, więc dostał{A?|a} zadanie patrzenia, jak robią to inni, co jest gorsze.
Rana, którą {A} {A?odniósł|odniosła} {kmap_at} {kd_ago}, nadal sączy się rankami, a {A} przewiązuje ją {cloth_ins}, zanim ktokolwiek wstanie.
== inj.healed
{A} {A?zdjął|zdjęła} dziś opatrunek. To miejsce na {site_loc} to blada nowa rzecz, pomarszczona i bez włosa, a wszystkich zaproszono, żeby obejrzeli.
Rana na {site_loc} zasklepiła się blizną po {kmap_loc}, a {A} wodzi po niej palcem, kiedy myśli, że nikt nie widzi.
== scar.cb
Blizna po {kmap_loc} bieleje u {A?niego|niej} na mrozie i po niej poznaje się pogodę.
== grief.title
{A} nadal stawia dwie miski
{D}: nie ma {D?go|jej} {dgo}
{A} nie może przestać patrzeć na pryczę {D?zmarłego|zmarłej}
{A} obchodzi mur za {D?zmarłego|zmarłą}
== grief.line
Prycza jest zasłana ciasno, rogi równo, i {A} nikomu nie pozwoli na niej usiąść.
{A} znalazł{A?|a} w kieszeni płaszcza {dpos_acc} po {D?zmarłym|zmarłej}, trzymał{A?|a} to w ręku i długo nic nie mówił{A?|a}.
{A} wciąż przyłapuje się na tym, że odwraca się w drzwiach, żeby coś powiedzieć {D?zmarłemu|zmarłej}.
{A} przez tydzień obchodził{A?|a} mur nocami i nikt nie pytał dlaczego ani nie próbował {A?go|jej} powstrzymać.
{A} nie może jeść zupy, którą zwykle gotował{D?|a} {D}, i nie może jej też wylać.
== death.title
{D} {D?odszedł|odeszła}
Pochowano {D?go|ją} obok {kplace_gen}
{A} umył{A?|a} ręce {D?zmarłego|zmarłej}
{A} czuwał{A?|a} przy {D?zmarłym|zmarłej}
== death.line
{D} umarł{D?|a} z raną na {dsite_loc} nadal owiniętą {dcloth_ins}, szarą od tygodnia noszenia.
{A} czuwał{A?|a} przy ciele, bo wydawało się złe, żeby leżało samo, i opowiadał{A?|a} mu wszystkie małe zwyczajne rzeczy, na które nie było czasu.
{A} {A?owinął|owinęła} {D?go|ją} w koc i związał{A?|a} sznurem, ciasno, a sznur wgryzł się w wełnę, która pachniała {D?nim|nią}.
Dzieciom powiedziano i niektóre zrozumiały.
{B} dostał{B?|a} po {D?zmarłym|zmarłej} {dposx_acc} i położył{B?|a} to tam, gdzie pada światło.
Miejsce {D?zmarłego|zmarłej} przy stole zostało puste i nikt nie postawił miski, a potem {A} postawił{A?|a}.
== death.rel
{D} uczył{D?|a} {C} odczytywać wiatr z kawałka materiału; {C} przywiązał{C?|a} ten kawałek do krzyża.
{C} prawie nie odstępował{C?|a} {D?zmarłego|zmarłej} od miesiąca i wracał{C?|a} z grobu sam{C?|a}.
== prep.title
{A} rozkłada na stole następną wyprawę
Przed następną wyprawą {A} sprawdza sprzęt
{A} rozrysował{A?|a} następne natarcie mąką
{A} nie powie gdzie, powie tylko, że nie będzie cicho
== prep.event
{A} nakreślił{A?|a} kredą {map_acc} na stole, {place} w jednym rogu, a {place2} w drugim, i dał{A?|a} {enemies_dat} trzy czarne kamienie przy drzwiach.
{A} znów {A?przeszedł|przeszła} kijem po ziemi przez {map_acc}: wejście przez {place_acc}, wyjście przez {place2_acc} i miejsce za schodami, gdzie można przeleżeć godzinę.
{A} mówi, że {enemies} zajmą {place_acc}, jeśli linie pójdą tak jak ostatnio, i chce tam karabin przed zmrokiem.
== prep.stock
W puszce jest {ammo_n}, a w szafce {food_n}; {A} zapisuje oba na ścianie kredą, jakby rzucał{A?|a} im wyzwanie, żeby spadły niżej.
{A} wydał{A?|a} {item_pl} {kplace_from} na następne natarcie: {n} na przód, reszta pod kluczem.
== prep.away
Skoro {AW} jest wciąż gdzieś tam, nikt nie chce mówić, jakie są szanse, więc {A} nic nie mówi i dwa razy sprawdza paski.
{A} zostawia lampę w oknie dla {AW_niego} i co godzinę przycina knot.
== prep.recent
Po {prev_map_loc} wczoraj ({prev_res}) {A} chce jeszcze jednego podejścia na tym samym terenie.
Po {prev_map_loc} wczoraj ({prev_res}) {A} chce, żeby tym razem poszło inaczej.
== rel.title
{A} i {B}
{A} i {B}: co zaszło między nimi
{A} i {B} — coś, co zauważyli wszyscy
{A}, {B} i drobiazg, który wszyscy zauważyli
== rel.rival.1
{A} i {B} {AB?założyli|założyły} się, kto wyniesie cięższy worek {map_from}; {A} przegrał{A?|a} i zapłacił{A?|a} kiszoną cebulą.
== rel.rival.2
{A} i {B} {AB?nie odzywali|nie odzywały} się przy kolacji. Znów poszło o łyżkę albo o pomysł łyżki, a ławka wokół ucichła.
== rel.rival.3
{B} zagrodził{B?|a} {A?mu|jej} drogę do drzwi i {B?wygarnął|wygarnęła} wszystko, co czekało rok. {A} wysłuchał{A?|a} do końca, pokiwał{A?|a} głową, powiedział{A?|a}: dobrze, i {A?wyszedł|wyszła}; to najbliższe przeprosinom, co mieli.
== rel.rival.4
{A} i {B} widziano, jak niosą jedną beczkę wody, każde za jeden uchwyt, nie patrząc na siebie. Ławka założyła się o rozejm.
== rel.sweet.1
{A} i {B} znów {AB?dostali|dostały} tę samą wartę i {AB?przerzucali|przerzucały} się dobrym posterunkiem, aż któreś ustąpiło.
== rel.sweet.2
{A} znalazł{A?|a} polny kwiat w blaszanym kubku na półce nad pryczą i nikomu nie powiedział{A?|a}, kto go tam postawił. {B} jest bardzo zajęt{B?y|a}.
== rel.sweet.3
{A} i {B} {AB?stali|stały} zbyt blisko przy piecu, ramię w ramię, bez dotykania, tak długo, jak gotowała się zupa.
== rel.sweet.4
{A} i {B} {AB?wyszli|wyszły} razem tylnymi drzwiami przed świtem, z jedną ręką na lampie i drugą na rękawie tego drugiego. {camp_at} udają, że nic nie zauważyli, i mówią o niczym innym.
== rel.mentor.1
{B} usiadł{B?|a} za murem z {A?nim|nią} i uczył{B?|a} {A?go|ją} odczytywać wiatr z kawałka materiału.
== rel.mentor.2
{A} naprawił{A?|a} pasek tak, jak miesiąc temu pokazywał{B?|a} {B}, a {B} udawał{B?|a} zaskoczenie.
== rel.mentor.3
{B} podał{B?|a} {A?mu|jej} lepszy nóż, rękojeścią do przodu, i nie powiedział{B?|a} dlaczego.
== rel.mentor.4
{A} poprawił{A?|a} {B} na oczach wszystkich, a {B} podziękował{B?|a} ze ściśniętą szczęką, i naprawdę tak myślał{B?|a}.
== rel.kin.1
{A} i {B} dzielą koc i nos, i nikt nie pamięta, kto z nich jest starszy.
== rel.kin.2
{A} ostrzygł{A?|a} {B?go|ją} na ganku, a ścinki poleciały na grządki z warzywami.
== rel.kin.3
{B} {B?wniósł|wniosła} całe wiadro po schodach, żeby {A} nie musiał{A?|a}; {A} pozwolił{A?|a} i podziękował{A?|a} bez proszenia.
== rel.kin.4
{A} pożyczył{A?|a} {B?mu|jej} dobry płaszcz na wartę i nie dał{A?|a} po sobie poznać, że przeszkadza mu, iż wrócił pachnący cudzym dymem.
== prof.title
{A} i {poss_short}
Co {A} nosi przy sobie
{A} nie lubi {fear}
Drobiazgi o {A}
== prof.poss
{A} trzyma {poss_acc} w wewnętrznej kieszeni i dotyka tego, kiedy lampy przygasają.
{A} ma {poss_acc} i nikomu nigdy nie wolno było tego potrzymać.
{A} zgubił{A?|a} {poss_acc} na jeden dzień i wywrócił{A?|a} {camp_acc} do góry nogami, aż rzecz znalazła się pod butem.
== prof.fear
{A} boi się {fear}: {fear_what}.
{A} nigdy tego nie mówi, ale boi się {fear}: {fear_what}.
== prof.past
{A}: {past}, i widać to po tym, jak nakrywa do stołu albo jak patrzy na drzwi.
Przed tym wszystkim: {past}; {A} wspomina o tym tylko po ciemku.
== prof.calm
{A} słucha wszystkiego i odpowiada na jedną trzecią, a {camp_at} nauczono się czytać pozostałe dwie trzecie z twarzy.
== prof.hot
{A} rzucił{A?|a} butem o ścianę z niczego, potem go {A?podniósł|podniosła} i wyczyścił{A?|a}, a wszyscy zgodzili się, że nic nie widzieli.
== prof.anxious
{A} sprawdza zasuwę cztery razy, a okno dwa, i {camp_at} śpi się przez to lepiej.
== prof.dry
{A} powiedział{A?|a}, że zupa to smak, do którego trzeba się przyzwyczaić, i nikt jeszcze się nie przyzwyczaił.
== prof.tender
{A} oddał{A?|a} ostatni kawałek chleba dziecku, które o niego nie prosiło, i powiedział{A?|a}, że nie jest głodn{A?y|a}.
== prof.stubborn
{A} odrzucił{A?|a} rady trzech osób, jak łatać dach, załatał{A?|a} go po swojemu, przy najbliższym deszczu okazało się, że miał{A?|a} rację, i nic o tym nie powiedział{A?|a}.
== quip.good.calm
„Damy radę”, powiedział{A?|a} {A} i po raz pierwszy zabrzmiało to jak plan.
„Zawsze {A?lubiłem|lubiłam}, kiedy wraca cisza”, powiedział{A?|a} {A}, patrząc w piec.
== quip.good.hot
„Następnym razem idę z tobą”, powiedział{A?|a} {A}, waląc w stół tak, że kubki podskoczyły.
== quip.good.anxious
„To nie potrwa”, {A?mruknął|mruknęła} {A}, i i tak {A?poszedł|poszła} sprawdzić zasuwę.
== quip.good.dry
„Tysiąc lat pokoju, więc”, powiedział{A?|a} {A} sucho jak kość. „Do czwartku.”
== quip.good.tender
„Chodź jeść, należy ci się”, powiedział{A?|a} {A}, a głos był miększy niż słowa.
== quip.good.stubborn
„{A?Mówiłem|Mówiłam}, że wytrzyma”, powiedział{A?|a} {A}, do nikogo w szczególności.
== quip.bad.calm
„Jeden zły dzień to nie zły żywot”, powiedział{A?|a} {A} i, o ile ktokolwiek mógł ocenić, naprawdę tak myślał{A?|a}.
== quip.bad.hot
„Gdybym tam {A?był|była}”, powiedział{A?|a} {A}, i nie dokończył{A?|a}, i nie musiał{A?|a}.
== quip.bad.anxious
„A jeśli przyjdą tu następni?”, zapytał{A?|a} {A} i nikt nie chciał odpowiedzieć.
== quip.bad.dry
„No cóż”, powiedział{A?|a} {A}, „poszło mniej więcej tak dobrze jak ostatnio.”
== quip.bad.tender
„Siadaj”, powiedział{A?|a} {A}, „siadaj, jedz, poczeka”, i {A?przesunął|przesunęła} miskę przez stół.
== quip.bad.stubborn
„Wracamy”, powiedział{A?|a} {A}. „Wracamy i nie przegrywamy dwa razy.”
"""
