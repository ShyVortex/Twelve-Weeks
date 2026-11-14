"""Polish clan saga templates, part 3: line for line parallel to clan_saga_text3.py (the memory scenes).  See clan_saga_pl.py for the rules."""
TEXT = r"""
== arc.tie
Tego samego wieczoru o niczym innym nie mówiono poza {map_ins}, a w każdej rozmowie prędzej czy później {A?pojawiał|pojawiała} się {A}.
{map_at} strzelanina trwała mimo wszystko; a {camp_at} liczył{A?|a} się tylko {A}.
{A} przewijał{A?|a} się w każdej rozmowie o {map_loc}, nawet gdy o {map_loc} wcale nie mówiono.
Wrócono {map_from} i pierwsze pytanie brzmiało: co z {A?nim|nią}?
Nikt nie mógł ustalić wyniku {map_gen} tamtej nocy; ten drugi rachunek był zbyt głośny.
Nawet {k_dn} {map_at} wydawało się małe przy tym.
Ktoś zapytał, czy ta cena była warta {map_gen}, i nikt nie odpowiedział, bo odpowiedź nosiła imię: {A}.
== use.title
{A} zużył{A?|a} część tego, co przyniesiono {kmap_from}
Ubywa {item_short_gen} {kplace_from}
{A} otworzył{A?|a} zapasy z dnia {kd}
{A} {A?sięgnął|sięgnęła} do łupu z dnia {kd}
To, co zostawiono nam {kmap_from}, zaczyna się kończyć
{A} prowadzi rachunek tego, co przyniesiono {kmap_from}
== use.ammo
{A} zużył{A?|a} {n} z {item_pl_gen} {kmap_from} (znalezionych {kd_ago}) na strzelanie do celu za murem i każdy strzał był lekcją dla młodszych.
{A} wyliczył{A?|a}, co zostało z {item_pl_gen} {kplace_from}: {n_left}. Nie starczy na miesiąc i {A} powiedział{A?|a} to na głos.
{A} zużył{A?|a} {n} z {item_pl_gen} {kplace_from}, żeby nauczyć dzieciaka stać nieruchomo, i trzymał{A?|a} go za łokieć, aż oddech dzieciaka zwolnił.
{A} {A?wziął|wzięła} {n} z {item_pl_gen} {kmap_from}, załadował{A?|a} nimi stary karabin i {A?poszedł|poszła} usiąść na murze o zmierzchu; teraz {n_left}.
{A} racjonuje {item_pl} znalezione {kd_ago} {kplace_at}: {n} na nocną wartę, {n_left}.
== use.food
{A} ugotował{A?|a} {item_pl} {kplace_from} na wieczór i odmówił{A?|a} modlitwę, o którą nikt nie prosił.
{A} otworzył{A?|a} {item_pl} znalezione {kd_ago} {kmap_at}, a wszyscy {camp_at} poczuli zapach, zanim trafiło na talerz.
{A} {A?rozciągnął|rozciągnęła} {item_pl} {kmap_from} wodą i korzeniami i nikt nie odważył się powiedzieć, jakie to rzadkie.
{A} dał{A?|a} dzieciom {item_pl} {kplace_from}, po łyżce, i patrzył{A?|a}, jak jedzą, jakby uczyły się, jak to się robi.
{A} trzymał{A?|a} {item_pl} {kmap_from} na zły dzień, a dziś właśnie taki był.
== use.med
{A} zużył{A?|a} jedną sztukę z {item_pl_gen} {kplace_from} na gorączkę, która nie chciała spaść, i zapisał{A?|a} to w rejestrze małą, żałosną kreską.
{A} otworzył{A?|a} {item_pl} {kmap_from}, znalezione {kd_ago}, i {A?wziął|wzięła} się do starego zakażenia, które się pogarszało.
{A} powiedział{A?|a}, że {item_pl} {kplace_from} to jedyne szczęście, jakie {camp_at} znaleziono tego tygodnia, i zużył{A?|a} je.
{A} zszył{A?|a} chłopcu kolano ostatnim z {item_pl_gen} {kmap_from} i dał{A?|a} mu cukierka z ukrytej puszki.
{A} wyłożył{A?|a} {item_pl} {kmap_from} na stół, odłożył{A?|a} jedną sztukę z powrotem, a resztę {A?zamknął|zamknęła} na klucz.
== use.tool
{A} użył{A?|a} jednego z {item_pl_gen} {kplace_from} (dzień {kd}), żeby naprawić to, co było zepsute od wiosny, i {A?poszedł|poszła} szukać następnej rzeczy.
{A} jest dumn{A?y|a} z jednego z {item_pl_gen} {kmap_from} i pokazuje je każdemu, kto usiedzi spokojnie.
{A} naprawił{A?|a} zasuwę bramy jednym z {item_pl_gen} {kplace_from}; zamyka się teraz z kliknięciem, a {camp_at} wszyscy czują się przez to trochę wyżsi.
{A} załatał{A?|a} trzy buty jednym z {item_pl_gen} {kmap_from} (znalezionych {kd_ago}) i {A?odmówił|odmówiła} przyjęcia podziękowań.
{A} spędził{A?|a} popołudnie z jednym z {item_pl_gen} {kplace_from}, a wieczorem beczka na wodę przestała kapać.
== keepcb.title
{kitem} {kmap_from} znów się pojawia
{A} i {kitem} z dnia {kd}
{kitem} z dnia {kd} nadal w użyciu
{kmap_from} mamy {kitem_acc} i to znaczy więcej niż puszki
{kitem} {kplace_from} w każdej opowieści
== keepcb.chess
Na szachownicy {kplace_from} (dzień {kd}) rozgrywa się już turniej. {A}, {A?który|która} był{A?|a} zbyt dumn{A?y|a}, żeby poznać zasady, przegrał{A?|a} z sześciolatkiem i {A?przyjął|przyjęła} to z godnością.
{A} znalazł{A?|a} zaginionego czarnego skoczka w kurzu pod piecem i {A?wsunął|wsunęła} go z powrotem na szachownicę {kmap_from} bez słowa.
Szachownica {kmap_from} stoi teraz na długim stole. Dzieci grają kapslami i zużytymi łuskami, a {A} sędziuje z twarzą jak z kamienia.
Ktoś wystrugał nowego czarnego skoczka z drewnianej łyżki do szachownicy przyniesionej {kplace_from} i to najlepsza figura na planszy.
== keepcb.guitar
{A} nauczył{A?|a} się trzech nut na strunie {kplace_from}, brzmią jak drzwi; dzieci nucą je do siebie z pokoju do pokoju.
Struna gitarowa {kmap_from} jest teraz naciągnięta na pudełku po butach, a {A} uczy dzieci wygrywać jedną melodię.
{A} {A?nawinął|nawinęła} strunę {kplace_from} na wygięty gwóźdź i szarpał{A?|a} ją, aż wszyscy {camp_at} znali tę nutę.
== keepcb.comic
Komiks {kplace_from} jest czytany po raz czterdziesty; {A} robi głosy, a dzieci są już za duże, żeby dać się nabrać, ale przychodzą posłuchać.
{A} znów czytał{A?|a} na głos komiks {kmap_from}, zmyślając brakującą ostatnią stronę, i został{A?|a} poprawion{A?y|a} przez dziewięciolatka.
Komiks {kplace_from} oklejono taśmą pakową; ostatniej strony nadal brak, a ta brakująca jest najlepsza.
== keepcb.teddy
Miś {kmap_from} trafił do {B}, {B?który|która} zaprzecza, że to ją obchodzi, i śpi z ręką na jego uchu.
{A} przyszył{A?|a} nowe oko pluszowemu misiowi {kplace_from}, guzik z płaszcza zmarłego, a dzieci nadały mu imię, zanim przecięto nić.
Miś {kmap_from} siedzi cały dzień na półce nad piecem i pilnuje drzwi, a najmniejsze dzieci kiwają mu głową, wchodząc.
== keepcb.seeds
{A} zasadził{A?|a} nasiona {kplace_from} w pudełku po butach na parapecie, sprawdza je dwa razy dziennie i mówi, że wszystko w porządku. Nic jeszcze nie wzeszło.
Nasiona {kmap_from} nadal leżą w woreczku; {A} wyjmuje je i chowa z powrotem, jakby decydował{A?|a}, czy świat na nie zasługuje.
{A} wykopał{A?|a} małą grządkę za {camp_ins} na nasiona {kplace_from} i dwa razy obchodzi ją przed snem.
== keepcb.cards
Grają teraz talią {kplace_from}, bez siódemki trefl, którą {A} zastąpił{A?|a} nową, wyciętą z pudełka po racjach, i nigdy nie dał{A?|a} się przyłapać.
Talia kart {kmap_from} zrobiła się miękka jak szmaty, a partia remika trwa już dziewięć dni.
{A} nauczył{A?|a} się sztuczki z kartami {kplace_from} i pokazał{A?|a} ją dzieciom; dzieci ukradły talię i same się jej nauczyły.
== keepcb.harmonica
Harmonijka {kplace_from} wędruje po {camp_loc} z rąk do rąk; {A} jest jedynym, kto potrafi wydobyć z niej prawdziwą melodię, i tylko gdy nikt nie patrzy.
{A} zagrał{A?|a} na murze o zmierzchu na harmonijce {kmap_from}, trzy wolne nuty, i wartownik po drugiej stronie przestał rozmawiać.
Harmonijką {kplace_from} obudzono dziś rano dzieci, rzucono nią, odzyskano ją i nadal działa.
== inj.title
{A} nadal oszczędza {site_acc}
{A}: rana na {site_loc} nie zapomniała o {kmap_loc}
Jak się ma {A}
{A} nie przyzna, że nadal boli
{A} i rana {kmap_from}
Pięć dni później {A} nadal nie jest w formie
== inj.mid
{A?Jego|Jej} rana na {site_loc} jest nadal owinięta, opatrunek poszarzał, a {A} robi jedną ręką rzeczy na jedną rękę i przeklina te na dwie.
{A} nie może {job_neg} z kontuzją {site_gen}, więc dostał{A?|a} zadanie patrzenia, jak robią to inni, co jest gorsze.
Rana, którą {A} {A?odniósł|odniosła} {kmap_at} ({kd_ago}), nadal sączy się rankami, a {A} przewiązuje ją przed świtem, zanim ktokolwiek wstanie.
{A} przyłapał{A?|a} się na rozruszywaniu bolącego miejsca na {site_loc}, kiedy myślał{A?|a}, że nikt nie patrzy, i skrzywił{A?|a} się.
Rana, którą {A} nosi na {site_loc} od dnia {kd} ({kmap_from}), ma kolor śliwki, a {A} mówi, że to właściwy kolor.
{A} wzdryga się, ilekroć ktoś go ociera, i udaje, że patrzy na coś na podłodze.
{A} budził{A?|a} się dwa razy w nocy, czując ogień na {site_loc}, i nikomu o tym nie mówił{A?|a}.
== inj.healed
{A} {A?zdjął|zdjęła} dziś opatrunek. To miejsce na {site_loc} to blada nowa rzecz, pomarszczona i bez włosa, a wszystkich zaproszono, żeby obejrzeli.
Rana na {site_loc} zasklepiła się blizną po {kmap_loc}, a {A} wodzi po niej palcem, kiedy myśli, że nikt nie widzi.
{A} {A?odwinął|odwinęła} ostatni kawałek opatrunku i poruszył{A?|a} {site_ins}; wytrzymało; dzieci klaskały.
Rana po {kmap_loc} wreszcie się zamknęła. {A} będzie nosić znak i już {A?zaczął|zaczęła} opowiadać tę historię źle.
{A} wrzucił{A?|a} brudny opatrunek do ognia, patrzył{A?|a}, jak płonie, i powiedział{A?|a}, że to koniec.
== scar.cb
Blizna po {kmap_loc} bieleje u {A?niego|niej} na mrozie i po niej poznaje się pogodę.
{A} został{A?|a} zapytan{A?y|a} o bliznę na {site_loc} i opowiedział{A?|a} trzy różne historie z rzędu.
{A} dotyka blizny po {kmap_loc} przed każdą wyprawą, szybko, jak ktoś, kto się żegna.
{A?Jego|Jej} blizna na {site_loc} po {kmap_loc} znów przyciągnęła dziecięcy palec; {A} pozwolił{A?|a}.
{A} {A?zaczął|zaczęła} opowiadać o {kmap_loc} tak, jakby to było zabawne.
== grief.title
{A} nadal stawia dwie miski
{D}: nie ma {D?go|jej} {dgo}
{A} nie może przestać patrzeć na pryczę {D?zmarłego|zmarłej}
{A} obchodzi mur za {D?zmarłego|zmarłą}
{A} nie pozwala nikomu ruszyć butów {D?zmarłego|zmarłej}
Bez {D?zmarłego|zmarłej} jest ciszej
== grief.line
Prycza jest zasłana ciasno, rogi równo, i {A} nikomu nie pozwoli na niej usiąść.
{A} znalazł{A?|a} w kieszeni płaszcza {dpos_acc}, długo to trzymał{A?|a} i odłożył{A?|a} dokładnie tam, gdzie leżało.
{A} wciąż przyłapuje się na tym, że odwraca się w drzwiach, żeby coś powiedzieć {D?zmarłemu|zmarłej}.
{A} przez tydzień obchodził{A?|a} mur nocami i nikt nie pytał dlaczego ani nie próbował {A?go|jej} powstrzymać.
{A} nie może jeść zupy, którą zwykle gotował{D?|a} {D}, i nie może jej też wylać.
{A} mówi: {D}, gdy gotuje się czajnik, jakby to było polecenie.
{A} siedział{A?|a} na stopniu, trzymając {dpos_acc} w obu dłoniach, i zmierzch zapadł niepostrzeżenie.
{A} pokroił{A?|a} chleb na jeden kawałek za dużo, a potem nie zjadł{A?|a} tego jednego kawałka za dużo.
== death.title
{D} {D?odszedł|odeszła}
Pochowano {D?go|ją} obok {kplace_gen}
{A} umył{A?|a} ręce {D?zmarłego|zmarłej}
{A} czuwał{A?|a} przy {D?zmarłym|zmarłej}
{D} nie doczekał{D?|a} rana
{A} {A?owinął|owinęła} {D?go|ją} w dobry koc
== death.line
{D} umarł{D?|a} z raną na {dsite_loc} nadal owiniętą {dcloth_ins}, szarą od tygodnia noszenia.
{A} czuwał{A?|a} przy ciele, bo wydawało się złe, żeby leżało samo, i opowiadał{A?|a} mu wszystkie małe zwyczajne rzeczy, na które nie było czasu.
{A} {A?owinął|owinęła} {D?go|ją} w koc i związał{A?|a} sznurem, ciasno, a sznur wgryzł się w wełnę, która pachniała {D?nim|nią}.
Dzieciom powiedziano i niektóre zrozumiały.
{B} dostał{B?|a} po {D?zmarłym|zmarłej} {dposx_acc} i położył{B?|a} to tam, gdzie pada światło.
Miejsce {D?zmarłego|zmarłej} przy stole zostało puste i nikt nie postawił miski, a potem {A} postawił{A?|a}.
Grób nie jest głęboki; ziemia pełna kamieni i korzeni. {A} kopał{A?|a}, aż poszła krew z dłoni, i kopał{A?|a} dalej.
Wyniesiono {D?go|ją} o świcie na drzwiach zdjętych z zawiasów, a drzwi nie wrócą już na miejsce.
{A} {A?zamknął|zamknęła} {D?zmarłemu|zmarłej} oczy dwoma palcami i poczuł{A?|a}, że ręka jest jeszcze ciepła.
{D} umarł{D?|a} w nocy przy przygaszonej lampie, a ostatnie słowo było imieniem, którego nikt tam nie znał.
{A} stał{A?|a} przy grobie, aż reszta odeszła, i stał{A?|a} dalej.
== prep.title
{A} rozkłada na stole następną wyprawę
Przed następną wyprawą {A} sprawdza sprzęt
{A} rozrysował{A?|a} następne natarcie mąką
{A} nie powie gdzie, powie tylko, że nie będzie cicho
{A} ostrzy rzeczy i nic nie mówi
Plecak przy drzwiach jest pełny, a {A} chce, żeby był pełniejszy
{A} obchodził{A?|a} mur o zmierzchu, licząc to, czego brakuje
== prep.event
{A} nakreślił{A?|a} kredą {map_acc} na stole, {place} w jednym rogu, a {place2} w drugim, i dał{A?|a} {enemies_dat} trzy czarne kamienie przy drzwiach.
{A} znów {A?przeszedł|przeszła} kijem po ziemi przez {map_acc}: wejście przez {place_acc}, wyjście przez {place2_acc} i miejsce za schodami, gdzie można przeleżeć godzinę.
{A} mówi, że {enemies} zajmą {place_acc}, jeśli linie pójdą tak jak ostatnio, i chce tam karabin przed zmrokiem.
{A} {A?podniósł|podniosła} latarnię nad mapą {map_gen}, znalazł{A?|a} {place_acc} i {A?przycisnął|przycisnęła} kciukiem, mocno, jakby mogło uciec.
{A} chce dwóch do utrzymania {place_gen} i dwóch do obejścia {place2_gen}, i cały wieczór kazał{A?|a} dzieciom nie słuchać.
{A} trzy razy powtórzył{A?|a} ten sam plan, za każdym razem trochę inny, i powiedział{A?|a}, że żaden nie przetrwa pierwszego strzału.
{A} narysował{A?|a} {place2_acc} na odwrocie kartki z racjami i zapytał{A?|a}, kto był tam w środku ostatni.
== prep.stock
W puszce jest {ammo_n}, a w szafce {food_n}; {A} zapisuje oba na ścianie kredą, jakby rzucał{A?|a} im wyzwanie, żeby spadły niżej.
{A} wydał{A?|a} {item_pl} {kplace_from} na następne natarcie: {n} na przód, reszta pod kluczem.
{A} dwa razy przeliczył{A?|a} zapasy, za każdym razem brakowało jednego, i uznał{A?|a}, że to wina liczenia.
{A} rozłożył{A?|a} {item_pl} {kplace_from} do trzech toreb, żeby jeden błąd nie mógł zabrać wszystkiego.
{A} powiedział{A?|a}, że {item_pl} {kplace_from} to jedyne, co dzieli wszystkich {camp_at} od bardzo złego miesiąca.
== prep.away
Skoro {AW} jest wciąż gdzieś tam, nikt nie chce mówić, jakie są szanse, więc {A} nic nie mówi i dwa razy sprawdza paski.
{A} zostawia lampę w oknie dla {AW_niego} i co godzinę przycina knot.
{A} zostawił{A?|a} bramę niezaryglowaną dla {AW_niego} i spał{A?|a} w poprzek wejścia.
W każdym planie, który układa {A}, jest gdzieś {AW}, i każdy plan ma lukę o kształcie {AW_jego} nieobecności.
== prep.recent
Po {prev_map_loc} wczoraj ({prev_res}) {A} chce jeszcze jednego podejścia na tym samym terenie.
Po {prev_map_loc} wczoraj ({prev_res}) {A} chce, żeby tym razem poszło inaczej.
Po {prev_map_loc} ({prev_res}) {A} zapisał{A?|a} sobie na marginesie: sprawdzić dach.
{A} {A?przeszedł|przeszła} ze zwiadowcami wczorajszy dzień {prev_map_at} ({prev_res}) krok po kroku i znalazł{A?|a} miejsce, w którym się odwrócił.
== rel.title
{A} i {B}
{A} oraz {B}
{A} i {B}: coś, co zauważyli wszyscy
{A}, {B} i drobiazg, który wszyscy zauważyli
{A} i {B} — wszyscy to widzieli
{A} i {B}: co zaszło między nimi
== rel.rival.1
{A} i {B} założyli się, kto wyniesie cięższy worek z wyprawy; {A} przegrał{A?|a} i zapłacił{A?|a} kiszoną cebulą.
{AB?Sięgnęli|Sięgnęły} jednocześnie po ostatnie krzesło, {A} i {B}, i żadne nie chciało oddać, a teraz krzesło jest złamane na pół.
{A} opowiedział{A?|a} historię ostatniej wyprawy ze sobą w roli głównej; {B} opowiedział{B?|a} ją ze sobą w roli głównej; obie historie spotkały się w drzwiach.
== rel.rival.2
{A} i {B} nie odzywali się przy kolacji. Znów poszło o łyżkę albo o pomysł łyżki, a ławka wokół ucichła.
{A} i {B} {AB?pokłócili|pokłóciły} się o to, kto celniej strzela, co skończyło się zawodami w strzelaniu do puszek, które wygrał{B?|a} {B}, a które {A} podważał{A?|a}.
{A} przestawił{A?|a} buty, które {B} zostawił{B?|a} przy piecu, pod drzwi, a {B} przestawił{B?|a} je z powrotem, i buty wędrują już cały tydzień.
== rel.rival.3
{B} zagrodził{B?|a} {A?mu|jej} drogę do drzwi i {B?wygarnął|wygarnęła} wszystko, co czekało rok. {A} wysłuchał{A?|a} do końca, pokiwał{A?|a} głową, powiedział{A?|a}: dobrze, i {A?wyszedł|wyszła}; to najbliższe przeprosinom, co mieli.
{A} i {B} {AB?wyjaśnili|wyjaśniły} to sobie za agregatem, głośno, i {AB?wrócili|wróciły} z rozciętymi wargami i tym samym uśmiechem, którego nikt nie umiał wyjaśnić.
{A} i {B} byli razem na murze i oboje usłyszeli hałas, {AB?ruszyli|ruszyły} ku niemu naraz i {AB?walczyli|walczyły} z tym razem, plecami do siebie, a potem nic o tym nie {AB?mówili|mówiły}.
== rel.rival.4
{A} i {B} widziano, jak niosą jedną beczkę wody, każde za jeden uchwyt, nie patrząc na siebie. Ławka założyła się o rozejm.
{A} odkroił{A?|a} {B?mu|jej} kawałek dobrego chleba. {B} zjadł{B?|a} go. Żadne nie powiedziało ani słowa. Ławka nie jest pewna, co widziała.
{A} i {B} razem {AB?trzymali|trzymały} nocną wartę, a gdy wzeszło słońce, jedno spało na ramieniu drugiego.
== rel.sweet.1
{A} i {B} znów dostali tę samą wartę i przerzucali się dobrym posterunkiem, aż któreś ustąpiło.
{A} zachował{A?|a} {B?mu|jej} miejsce na ławce przy piecu, a potem udawał{A?|a}, że to dla kogoś innego.
{A} i {B} widziano, jak śmieją się do beczki z wodą, z powodów, które nie wytrzymały wyjaśnienia.
== rel.sweet.2
{A} znalazł{A?|a} polny kwiat w blaszanym kubku na półce nad pryczą i nikomu nie powiedział{A?|a}, kto go tam postawił. {B} jest bardzo zajęt{B?y|a}.
{A} i {B} {AB?dzielili|dzieliły} koc na murze z zimna i oboje twierdzą, że to przez pogodę.
{B} przyszył{B?|a} do {A?jego|jej} płaszcza guzik, źle, czerwoną nicią, i {A} nie pozwolił{A?|a} nikomu go poprawić.
== rel.sweet.3
{A} i {B} stali zbyt blisko przy piecu, ramię w ramię, bez dotykania, tak długo, jak gotowała się zupa.
{A} i {B} {AB?siedzieli|siedziały} na dachu po zmroku i {AB?liczyli|liczyły} gwiazdy, aż żadne nie pamiętało liczby.
{A} oddał{A?|a} {B?mu|jej} resztę herbaty, a {B} posłał{B?|a} {A?mu|jej} spojrzenie, które {camp_at} analizują do dziś.
== rel.sweet.4
{A} i {B} wyszli razem tylnymi drzwiami przed świtem, z jedną ręką na lampie i drugą na rękawie tego drugiego. {camp_at} udają, że nic nie zauważyli, i mówią o niczym innym.
{A} i {B} dzielą teraz jedną pryczę, a stara prycza jest półką na rzeczy i nikt nie powiedział ani słowa.
{A} i {B} biorą tę samą wartę, każdą wartę, od tygodnia, a inni zaczęli ich zastępować bez proszenia.
== rel.mentor.1
{B} {B?usiadł|usiadła} za murem i uczył{B?|a} {A?go|ją} odczytywać wiatr z kawałka materiału.
{B} pokazał{B?|a} {A?mu|jej}, jak nosić karabin, żeby nie stukał o futrynę.
{B} kazał{B?|a} {A?mu|jej} wymieniać na głos nazwy wzgórz po kolei, trzy razy, aż {A} umiał{A?|a} je wymienić przez sen.
== rel.mentor.2
{A} naprawił{A?|a} pasek tak, jak miesiąc temu pokazywał{B?|a} {B}, a {B} udawał{B?|a} zaskoczenie.
{A} zadał{A?|a} pytanie, na które {B} czekał{B?|a} rok, aż ktoś je zada.
{A} sam{A?|a} znalazł{A?|a} słabe miejsce w dachu, a {B} opowiada o tym wszystkim od tamtej pory.
== rel.mentor.3
{B} podał{B?|a} {A?mu|jej} lepszy nóż, rękojeścią do przodu, i nie powiedział{B?|a} dlaczego.
{B} oddał{B?|a} {A?mu|jej} stary płaszcz i powiedział{B?|a}, że potrzeba młodszych pleców, żeby go znosić.
{B} powierzył{B?|a} {A?mu|jej} klucze do szafki i cały czas patrzył{B?|a} {A?mu|jej} na twarz.
== rel.mentor.4
{A} poprawił{A?|a} {B?go|ją} na oczach wszystkich, a {B} podziękował{B?|a} ze ściśniętą szczęką, i naprawdę tak myślał{B?|a}.
{A} uczy teraz lekcji, których uczył{B?|a} {B}, a {B} słucha z tyłu.
{B} powiedział{B?|a}, że {A} nie ma się już od {B?niego|niej} czego uczyć, co było kłamstwem i darem.
== rel.kin.1
{A} i {B} dzielą koc i nos, i nikt nie pamięta, kto z nich jest starszy.
{A} i {B} kończyli nawzajem swoje zdania przy kolacji, a potem {AB?kłócili|kłóciły} się, czyje to było zdanie.
{A} i {B} {AB?spali|spały} plecami do siebie przy wystygłym piecu, kiedy ich znaleziono, jak dwie połówki bochenka.
== rel.kin.2
{A} ostrzygł{A?|a} {B?go|ją} na ganku, a ścinki poleciały na grządki z warzywami.
{A} i {B} {AB?wymieniali|wymieniały} tę samą kurtkę trzy razy w tygodniu i nigdy nie pasowała żadnemu z dwojga.
{A} i {B} {AB?pokłócili|pokłóciły} się o ostatnie masło, potem je {AB?podzielili|podzieliły}, a potem znów {AB?pokłócili|pokłóciły} się o nóż.
== rel.kin.3
{B} {B?wniósł|wniosła} całe wiadro po schodach, żeby {A} nie musiał{A?|a}; {A} pozwolił{A?|a} i podziękował{A?|a} bez proszenia.
{A} stał{A?|a} na straży przed łaźnią, kiedy {B} się mył{B?|a}, i ławka to zauważyła.
{B} obudził{B?|a} {A?go|ją} o północy, żeby o nic nie zapytać, i siedział{B?|a} bezsennie do rana.
== rel.kin.4
{A} pożyczył{A?|a} {B?mu|jej} dobry płaszcz na wartę i nie dał{A?|a} po sobie poznać, że przeszkadza mu, iż wrócił pachnący cudzym dymem.
{A} i {B} odbyli długą rozmowę na murze, po której oboje ucichli, a potem poczuli się trochę lżej.
{A} wypisał{A?|a} na wewnętrznej stronie czapki imię: {B}, obok pozostałych.
== prof.title
{A} i {poss_short}
Co {A} nosi przy sobie
{A} nie lubi {fear}
Drobiazgi o {A}
{A} ma nawyk
Co {A} trzyma w wewnętrznej kieszeni
{A}: coś, czego nikt nie wie
== prof.poss
{A} trzyma {poss_acc} w wewnętrznej kieszeni i dotyka tego, kiedy lampy przygasają.
{A} ma {poss_acc} i nikomu nigdy nie wolno było tego potrzymać.
{A} zgubił{A?|a} {poss_acc} na jeden dzień i wywrócił{A?|a} {camp_acc} do góry nogami, aż rzecz znalazła się pod butem.
{A} śpi z {poss_ins} pod poduszką, a dzieci wymyśliły o tym historie.
{A} pokazał{A?|a} {poss_acc} jednemu z dzieci, które długo na to patrzyło i oddało bez słowa.
== prof.fear
{A} boi się {fear}: {fear_what}.
To nie tajemnica, że {A} boi się {fear}: {fear_what}.
{A} prędzej umrze, niż to powie, ale boi się {fear}: {fear_what}.
{A} kiedyś bał{A?|a} się {fear}, a teraz tylko się pilnuje: {fear_what}.
{A} boi się {fear} bardziej niż jakiejkolwiek kuli: {fear_what}.
== prof.past
{A} nigdy tego nie mówi, ale {camp_at} wszyscy wiedzą: {past}.
Każdy ma przeszłość, a {A?jego|jej} jest krótka: {past}.
{A} o tym nie mówi. Ludzie mówią tak: {past}.
Krąży plotka i {A} pozwala jej trwać: {past}.
== prof.calm
{A} słucha wszystkiego i odpowiada na jedną trzecią, a {camp_at} nauczono się czytać pozostałe dwie trzecie z twarzy.
{A} przesiedział{A?|a} godzinę przy przygaszonej lampie, nie robiąc nic, a kilka osób odeszło pocieszonych.
Złe sny dzieci opowiadają właśnie {A?jemu|jej}, a {A} żadnego z nich nie zapisuje.
== prof.hot
{A} rzucił{A?|a} butem o ścianę z niczego, potem go {A?podniósł|podniosła} i wyczyścił{A?|a}, a wszyscy zgodzili się, że nic nie widzieli.
{A} przegrał{A?|a} dziś rano kłótnię z drzwiami i drzwi zostaną wymienione.
{A} wygłosił{A?|a} przemowę o grafiku wody i skończył{A?|a}, zgłaszając się na każdą zmianę.
== prof.anxious
{A} sprawdza zasuwę cztery razy, a okno dwa, i {camp_at} śpi się przez to lepiej.
{A} policzył{A?|a} głowy przy kolacji, wyszło dobrze, i policzył{A?|a} jeszcze raz, i jeszcze.
{A} śpi w butach i mówi, że z zimna.
== prof.dry
{A} powiedział{A?|a}, że zupa to smak, do którego trzeba się przyzwyczaić, i nikt jeszcze się nie przyzwyczaił.
{A} zauważył{A?|a}, że optymizm już wypróbowano i nie wyszło, i dalej łatał{A?|a} dach.
{A} usłyszał{A?|a} prośbę o kilka słów i odparł{A?|a}: „Proszę, nie.”
== prof.tender
{A} oddał{A?|a} ostatni kawałek chleba dziecku, które o niego nie prosiło, i powiedział{A?|a}, że nie jest głodn{A?y|a}.
{A} otulił{A?|a} śpiącego psa kocem, został{A?|a} na tym przyłapan{A?y|a} i wszystkiemu zaprzeczył{A?|a}.
{A} usłyszał{A?|a} płacz dziecka za agregatem i usiadł{A?|a} obok bez słowa.
== prof.stubborn
{A} odrzucił{A?|a} rady trzech osób, jak łatać dach, załatał{A?|a} go po swojemu, przy najbliższym deszczu okazało się, że miał{A?|a} rację, i nic o tym nie powiedział{A?|a}.
{A} nie chce słyszeć, że studnia jest sucha, chodzi do niej co rano i co rano wraca z twarzą jak trzaśnięte drzwi.
{A} postanowił{A?|a} nauczyć psa aportować, a pies postanowił, że nie.
== res.win
Utrzymaliśmy {map_acc} mimo wszystko i tablica przy drzwiach dostała kolejną kreskę.
Wieść o wygranej obiegła wszystkich {camp_at}, zanim zdjęto buty.
Pod koniec mieliśmy w rękach {map_acc} i nikt nie mówił tego zbyt głośno.
To była wygrana i świadomość tego uczyniła wieczór lżejszym.
== res.loss
W końcu przegraliśmy {map_acc} i tablica przy drzwiach została pusta.
Porażka siedziała przy stole ze wszystkimi i nikt nie podał jej krzesła.
Przed zmrokiem przegrano {map_acc} i nikt nie chciał pierwszy tego powiedzieć.
To była porażka i długie twarze powiedziały to wcześniej niż ty.
"""
