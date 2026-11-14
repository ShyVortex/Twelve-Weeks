"""Polish clan saga templates, part 2: line for line parallel to clan_saga_text2.py (the match stories).  See clan_saga_pl.py for the rules."""
TEXT = r"""
== loss.title
{A} nie pytał{A?|a}, i to było dobre
To, co działo się {map_at}, kosztowało nas więcej, niż pokazuje tablica
{A} rozłożył{A?|a} bandaże, zanim ktokolwiek się odezwał
Lampy zostały przygaszone po {map_loc}
{enemies} odebrały nam {map_acc}
== loss.event
{map_at} wszystko rozstrzygnęło się w ostatnich dziesięciu minutach: trzymano {place_acc}, aż karabin kliknął pusto, a potem jeszcze chwilę gołymi rękami.
{map_at} powalono cię {place2_at}, podniesiono, uciekano i oglądano się, jak {enemies} wlewają się {place_to} niczym woda przez pękniętą balię.
Natarcie przez {place_acc}, {map_at} załamało się na drugiej fali. Widziano, jak linia się składa, słyszano znajomy głos wołający o medyka, który nie nadchodził, i wychodzono tą samą drogą, którą się weszło.
Nic z tego, co zrobiono {map_at}, nie było błędem i nic nie wystarczyło. {place_at} dawało, {place2_at} brało, a wychodziło się z {smell_ins} w ustach.
Przegrano {map_acc} na rogu: {place2_at} wytrzymano, {place_at} nie, a resztę rozstrzygnął jeden chybiony strzał w ciemności.
To był zły dzień i skończył się {place_at}, {map_at}: {enemies} na schodach i imiona swoich wykrzykiwane tam i z powrotem.
== loss.camp
{A} postawił{A?|a} czajnik i nie mówił{A?|a}, a to milczenie było życzliwe.
{A} stał{A?|a} przy oknie z zimnym kubkiem i wypatrywał{A?|a} na drodze ludzi, którzy już wrócili do domu.
{A} położył{A?|a} ci rękę na ramieniu, zabrał{A?|a} ją i {A?poszedł|poszła} myć garnek, który był już czysty.
Dzieci usłyszały bramę i pobiegły zobaczyć; zatrzymały się w drzwiach na widok twarzy i po cichu wróciły.
{A} dokładał{A?|a} do pieca nogi od krzeseł i powiedział{A?|a} piecowi, że się zdarza.
{A} {A?rozwinął|rozwinęła} bandaż z twojego nadgarstka, spojrzał{A?|a} na to, co było pod spodem, i {A?zawinął|zawinęła} go z powrotem.
== loss.b
{B} {B?trzasnął|trzasnęła} blaszanką o stół, potem ją {B?podniósł|podniosła} i patrzył{B?|a} na nią, jakby przeprosiła.
{B} twierdził{B?|a}, że {B?wziąłby|wzięłaby} {place2_acc} od lewej, i nikt nie miał serca przypominać, że za późno.
{B} przesiedział{B?|a} całą noc plecami do drzwi, z karabinem na kolanach i miną, jakby wyzywał{B?|a} ciemność.
{B} dwa razy przeliczył{B?|a} amunicję, zapisał{B?|a} liczby i podarł{B?|a} kartkę.
{B} {B?rzucił|rzuciła} żartem i nie wyszło, rzucił{B?|a} drugim i wyszło, a przy trzecim dzieci już się śmiały.
== loss.streak
{lossw} z rzędu. {A} przestał{A?|a} zaznaczać tablicę przy drzwiach i nikt nie pytał dlaczego.
W stołówce zaczęto głośno liczyć porażki przy kolacji; jest już {lossw}.
Kolejna porażka, po {prev_map_loc}: to już {lossw} z rzędu, a cisza przy kolacji ma ciężar.
== down.title
{A} trzymał{A?|a} lampę, kiedy padały przekleństwa
{A} zszył{A?|a} to, co rozdarto {map_at}
Szwy i opowieść o drzwiach
Wrócono na czyimś ramieniu, a {A} odsłonił{A?|a} ranę
{A} policzył{A?|a} wszystkie ślady po {map_loc}
== down.event
{map_at} kładziono cię na ziemię {dn_p}. {place_acc} pamięta się tylko jako zapach i sufit, i jako rękę, która wyciągnęła cię {place2_from} za pasek.
Powalono cię {dn_p} {map_at}: na widoku {place_at}, za schodami {place2_at} i jeszcze raz tam, gdzie nie chce się mówić.
{map_at} zraniono cię {dn_p} i za każdym razem czyjaś ręka sięgała po ciebie, zanim dosięgnął cię nóż {enemy_n}.
Na dół {dn_p} {map_at}, a ostatni raz {place_at} zostawił cię z widokiem własnego buta przez czerwoną mgłę i z pytaniem, czy w ogóle warto wstawać.
Nie chciano cię stąd wypuścić: {map_at} powalono cię {dn_p}, raz tuż po użyciu {wpn_gen}, raz na stopniu, którego nie było.
== down.care
{A} {A?przyciągnął|przyciągnęła} miskę, wypłukał{A?|a} piasek {site_from} wodą, która pachniała piecem, i {A?zamknął|zamknęła} ranę siedmioma szwami czarnej nici.
{A} wydłubał{A?|a} pęsetą odłamek szkła {site_from} i {A?uniósł|uniosła} go do lampy jak dowód rzeczowy.
{A} przemywał{A?|a} ranę, aż przestała być czerwona, potem zszył{A?|a} ją igłą, która przeszła przez trzy ognie, mrucząc coś pod nosem.
{A} {A?owinął|owinęła} ci {site_acc} {cloth_ins}, ciasno, i powiedział{A?|a}, co będzie, jeśli zamoknie.
{A} {A?wcisnął|wcisnęła} rozdartą skórę z powrotem, przytrzymał{A?|a} ją dwoma palcami i głosem człowieka czytającego przepis powiedział{A?|a}, że teraz zaboli.
{A} znalazł{A?|a} siniak wcześniej niż ty i przyłożył{A?|a} do niego zimną łyżkę, nie czekając na prośbę.
{A} {A?przegryzł|przegryzła} taśmę zębami i powiedział{A?|a}, że z raną na {site_loc} nie ma co udawać bohatera.
{A} zszył{A?|a} cię żyłką wędkarską, ostatnim kawałkiem szpuli z jeziora, którego nikt już nie pamięta.
== down.after
Ktoś zostawił na parapecie ugotowane jajko i nikt się nie przyznał.
{B} spojrzał{B?|a} na szwy, {B?gwizdnął|gwizdnęła} raz przez zęby i nic więcej nie powiedział{B?|a}.
Dzieciom powiedziano, że to zabawa, i nie dały się nabrać.
{B} siedział{B?|a} z tobą, aż lampa wypaliła się do końca, i opowiadał{B?|a} historię o psie.
{B} {B?położył|położyła} na tobie dodatkowy koc i udawał{B?|a}, że już tam leżał.
Spało się jak kamień, a po przebudzeniu bandaż był już zmieniony.
{B} {B?przyniósł|przyniosła} rosół i patrzył{B?|a}, aż kubek był pusty.
== down.you
Rana {ysite_at}, zszyta po {ymap_loc} w dniu {yd}, wytrzymała, a {A} powiedział{A?|a} to tak, jakby było to {A?jego|jej} osobiste zwycięstwo.
Nadal nosiło się ślad po {ymap_loc} (dzień {yd}), a teraz drugi obok niego, i {A} nic nie powiedział{A?|a} o tej parze.
== win.title
{A} zapalił{A?|a} dobrą lampę na cześć {map_gen}
Zajęliśmy {map_acc}, a dzieci już o tym wiedzą
{A} odkroił{A?|a} dodatkową pajdę za wygraną {map_at}
Wieść o wygranej {map_at} obiegła obóz wcześniej niż ty
{A} powiedział{A?|a} to cicho: dobra robota
Gorąca woda dziś wieczorem, na cześć {map_gen}
{A} powiesił{A?|a} nowy węzeł nad drzwiami na pamiątkę {map_gen}
== win.event
{enemies} załamały się {place_at}, {map_at}. Ostatnie z nich ścigano po schodach {place2_gen}, aż nie było już kogo ścigać, a nogi zrobiły się z wody.
Zajęto {map_acc}: {k_dn} i sucho w ustach. Kiedy strzały ucichły, wrócił {air}, a na najbliższym stopniu usiadło się, żeby się nim nacieszyć.
{map_at} przebijano się przez {place_acc}, utrzymano {place2_acc} i przebijano się znowu, a linia {enemies_gen} po prostu rozpadła się w rękach.
Czysta wygrana {map_at}: {k_dn}, oczyszczono {place_acc}, oczyszczono {place2_acc}, a potem długa droga do domu z pustym magazynkiem i pełnym sercem.
Wygrana. Nie było pewności, jak do tego doszło, tylko tyle, że ucichło {place_at}, potem {place2_at}, a potem cały teren {map_gen} stał i czekał, aż się stamtąd wyjdzie.
Do {camp_gen} weszło się z {map_ins} jeszcze na butach i z wygraną w kieszeni, a wartownik przy bramie uśmiechnął się, zanim cokolwiek powiedziano.
== win.camp
{A} usmażył{A?|a} ostatnie cebule na smalcu i pachniało jak w święto.
Dzieci przyniosły krzesło, żeby było gdzie usiąść, i nie wiedziały, co zrobić z resztą wieczoru.
{A} chciał{A?|a} każdego szczegółu i dostał{A?|a} połowę, a resztę dopisał{A?|a} sobie z luk.
{B} śpiewał{B?|a} coś pod nosem, hymn albo reklamę, nikt nie umiał powiedzieć.
{A} powiesił{A?|a} twoją mokrą kurtkę przy ogniu i opowiadał{A?|a} kurtce, jak bardzo wszyscy są dumni.
Czajnik gotował się i gotował, i nikt go nie zdejmował, bo dźwięk był dobry.
{A} policzył{A?|a} ludzi przy stole, wyszła dobra liczba, i policzył{A?|a} jeszcze raz, żeby mieć pewność.
{A} zawiązał{A?|a} dodatkowy węzeł na sznurze nad drzwiami, a sznur robi się ciężki.
== win.hs
{hs_nom}, a {A} kazał{A?|a} pokazać ręce i patrzył{A?|a} na nie, jakby mogły być niebezpieczne.
{hs_nom}, a {A} mówi, że nie ma takiego dźwięku, po czym powtarza ten dźwięk, cicho.
{hs_nom}, czysto, a {A} woła na ciebie już tylko po twoim celnym oku.
== win.after_loss
Po {prev_map_loc} {A} przestał{A?|a} wierzyć w takie dni, powiedział{A?|a} to głośno i trzy osoby zbeształy {A?go|ją} za te słowa.
Wczoraj {prev_map}, dziś {map}. {A} liczy oba razem i wychodzi {A?mu|jej} jeden dobry tydzień.
== exec.title
{A} nie dotknie noża, z którym wrócono
Co zrobiono {place_at}, {map_at}
W misce moczy się rękaw
{A} nie pytał{A?|a} o szczegóły i nikt ich nie podawał
Robota z bliska {map_at}
{A} umył{A?|a} ci ręce
== exec.event
Wykonano {ex_acc} {place_at}, {map_at}, tak blisko, że czuło się, jak ucieka ciepło, a jeden z nich zdążył powiedzieć imię, zanim skończono.
{ex_nom} {map_at}. Pierwsza poszła szybko, druga nie, a podłogę {place2_gen} trzeba było szorować.
Wchodzono z nożem {place_at}, {map_at} i wychodzono stamtąd cicho. Za plecami zostało: {ex_nom}. Ręce mokre po nadgarstki.
Trzy cięcia, kolano, dłoń na usta: {ex_nom} {place2_at}, {map_at}. Dźwięk, jaki wydaje człowiek, gdy się to robi, siedzi w zębach cały dzień.
{place_at}, {map_at} nie było miejsca na litość i żadnej nie okazano: {ex_nom}, a nóż jest teraz tępy.
== exec.react
{A} szorował{A?|a} plamy na twoim mankiecie solą i zimną wodą, nic nie mówił{A?|a} i szorował{A?|a} jeszcze długo po tym, jak plamy zniknęły.
{B} {B?przyniósł|przyniosła} miskę zupy i postawił{B?|a} ją trochę dalej, niż zwykle.
Dzieciom nie powiedziano i tak patrzyły na twoje ręce.
{A} powiedział{A?|a}, że to coś, co trzeba było zrobić, i że nie powinno to być łatwe, po czym {A?poszedł|poszła} w kąt, żeby po cichu zwymiotować.
{B} {B?położył|położyła} nóż na stole rękojeścią do ciebie, co jest rodzajem przebaczenia.
Przy kolacji nikt się nie odzywał, a łyżki były bardzo głośne.
{A} usiadł{A?|a} obok, nic nie mówił{A?|a} i został{A?|a} tak długo, jak trzeba było.
== exec.sw
{A} postawił{A?|a} przed tobą miskę gorącej wody i odwrócił{A?|a} wzrok, kiedy się myło.
== rev.title
{A} chciał{A?|a} znać liczbę rąk, do których dotarto
Podniesiono więcej, niż położono
{A} zapisał{A?|a} to w księdze: życia, nie zabici
Ręce, nie karabiny: rachunek {map_gen}
{A} mówi, że to jedyna kolumna warta prowadzenia
== rev.event
{map_at} podniesiono z podłogi {rv_acc}: kogoś {place_at}, kogoś {place2_at}, a jednego niesiono za pas przez sto metrów, kiedy {enemies} krzyczały z tyłu.
{map_at} wyciągnięto {rv_acc} i żadne z nich nie podziękowało w tamtej chwili; po tym poznaje się, że to się liczy.
Po {map_loc} wisi nad tobą dług oddechu: {rv_nom}. Jednego wyciągnięto {place_from} za ręce, z {smell_ins} w płucach i z kulą w skrzyni tuż przy uchu.
{map_at} doczołgano się do {rv_gen}: przez {place_acc}, pod stołem {place2_at}. Ostatni chwycił za nadgarstek tak mocno, że został siniak.
== rev.react
{A} powiedział{A?|a}, że tak to ma działać, i że niektórym trzeba to mówić.
{B} {B?położył|położyła} ci płasko dłoń na ramieniu, a dłoń lekko drżała.
{A} narysował{A?|a} na ścianie małe kółko za każdego, a kółek jest więcej, niż ktokolwiek się spodziewał.
Dzieci zrobiły ci koronę z drutu, którą trzeba będzie nosić dokładnie minutę.
{A} nic nie powiedział{A?|a}, a potem odkroił{A?|a} ci największy kawałek chleba, bez ceregieli.
{B} powiedział{B?|a}, że {B?zrobiłby|zrobiłaby} to samo, i po tym, jak to powiedział{B?|a}, było jasne, że nie jest pewn{B?y|a}.
== quiet.title
Płaski dzień {map_at}, a {A} to pochwala
{A} zapytał{A?|a}, a w odpowiedzi usłyszał{A?|a}, że w porządku
Znowu {map}, a w rejestrze nic
Wrócono w zabłoconych butach {map_from}
{A} wypełnił{A?|a} ciszę zupą
{map}: długie popołudnie, krótka historia
Żadnych historii {map_from}
== quiet.event
Dzień spędzono {map_at}: {k_dn}, dużo czekania {place_at} i dźwięk tego, że prawie nic się nie dzieje.
{map_at} nie było nic, co chciałoby się opowiadać. {place}, {place2}, {air} i równa pogoda strachu.
To był cichy dzień {map_at}, a cichy jest najlepszy: weszło się, wyszło się, a pomiędzy był {air}.
Wyprawa {map_at}: wrócono z kompletem palców. To cała historia i {A} jest z niej zadowolon{A?y|a}.
{map_at} czekano {place_at} przez większość wieczoru, a najdłuższy był powrót obok {place2_gen}.
{map_from} wrócono z obolałymi kolanami, {k_dn} na koncie i bez żadnego powodu, żeby opadać z sił.
== quiet.camp
{A} położył{A?|a} przed tobą łyżkę i z wielką powściągliwością zapytał{A?|a} o dzień.
{camp_at} pachniało dymem z drewna i gotowanymi korzeniami.
{A} chciał{A?|a} usłyszeć o {map_loc}, usłyszał{A?|a} jedno zdanie i zrobił{A?|a} z niego cały wieczór.
Ktoś w kącie grał w kamienie, a stukot kojąco działał.
{A} długo mówił{A?|a} o pogodzie i ani razu o wojnie.
Dwoje dzieci kłóciło się, kto usiądzie obok ciebie. Nikt cię nie pytał.
{A} naprawił{A?|a} pasek, kiedy jedzono, i nikt nie zauważył, aż było po wszystkim.
{A} powiedział{A?|a}, że droga była dziś cicha i że cisza denerwuje ludzi, a potem sam{A?|a} się z tego zaśmiał{A?|a}.
== bridge.same_map
{map}, {nth} w tym tygodniu: {A} zna pęknięcia na pamięć i przysięga, że to miejsce poluje na ciebie.
To znowu {map}, {nth} w tym tygodniu, a {A} zastanawia się na głos, czy mapa ma swojego ulubieńca.
{nth} {map_at}. {A} raz rozrysował{A?|a} plan mąką, a teraz rysuje go po ciemku.
{A} zauważa łagodnie, że to już {nth} {map_at} w tym tygodniu i że tamtejsza ziemia zna już twoje buty.
Znowu {map}: {nth} w tym tygodniu, a {A} {A?zaczął|zaczęła} zostawiać zapaloną lampę na tę okazję.
== bridge.you_scar
Twój szew {ysite_at}, założony po {ymap_loc} w dniu {yd}, jest teraz różową kreską.
Rana {ysite_at} po {ymap_loc} (dzień {yd}) nadal ciągnie przy sięganiu; {A} to zauważył{A?|a} i nic nie powiedział{A?|a}.
== hurt.line
{B} wpadł{B?|a} za tobą, z raną na {site_loc} rozdartą przez {cause_acc} {place2_at}, i usiadł{B?|a} bardzo ostrożnie na najbliższej skrzynce.
{B} oberwał{B?|a} {cause_ins} w {site_acc} {place2_at} i wracał{B?|a} z tą raną na własnych nogach, co było błędem.
{B} oberwał{B?|a} w {site_acc} {place_at}; wstał{B?|a}, przewrócił{B?|a} się, wstał{B?|a} znowu, a za drugim razem przyjaciele {B?go|ją} podtrzymali.
{B} {B?niósł|niosła} ranę na {site_loc} do domu jak paczkę, po trafieniu {cause_gen} {place2_at}, z białą twarzą, śmiejąc się z tego, co było najgorszym znakiem.
{B} stracił{B?|a} garść mięsa {site_from} przez {cause_acc} {place_at}, a szmata, którą to {B?owinął|owinęła}, zeszła mokra.
{B} {B?wszedł|weszła} do środka szar{B?y|a} i milcząc{B?y|a} po trafieniu {cause_gen} w {site_acc} i odmówił{B?|a} wszystkich krzeseł.
== mark.line
Stara rana {B?jego|jej} z ostatniej wyprawy nadal boli, a {A} zauważył{A?|a}, że {B} ją oszczędza.
{A} dał{A?|a} {B?mu|jej} lżejszą robotę, a {B} {B?przyjął|przyjęła} ją bez słowa.
{A} {A?zajął|zajęła} się {B?nim|nią} tego wieczoru i nie powiedział{A?|a}, dlaczego.
{A} zauważył{A?|a}, że {B} ma drżące ręce, i udawał{A?|a}, że nie.
== quip.good.calm
„Będzie dobrze”, powiedział{A?|a} {A}, i tym razem słowa zabrzmiały jak plan.
„{A?Mógłbym|Mogłabym} się do tego przyzwyczaić”, powiedział{A?|a} {A} do lampy i naprawdę tak myślał{A?|a}.
„Jedz powoli”, powiedział{A?|a} {A}. „Jutro będzie więcej.”
== quip.good.hot
„Powiedz jeszcze raz najlepszą część”, zażądał{A?|a} {A}, waląc w stół.
„{A?Mówiłem|Mówiłam} im”, powiedział{A?|a} {A}. „{A?Mówiłem|Mówiłam} wszystkim, że damy radę.”
„Następnym razem idę z wami”, powiedział{A?|a} {A} i każde słowo myślał{A?|a} serio.
== quip.good.anxious
„Nie zapeszaj”, {A?szepnął|szepnęła} {A} i zapukał{A?|a} trzy razy w stół.
„Wrócą”, powiedział{A?|a} {A}. „Zawsze wracają. Prawda?”
„Prześpię się, jak policzę wszystkich dwa razy”, powiedział{A?|a} {A}.
== quip.good.dry
„{A?Powiedziałbym|Powiedziałabym}, że mieliśmy szczęście”, powiedział{A?|a} {A}. „{A?Powiedziałbym|Powiedziałabym} też, żeby im nie mówić.”
„Smakuj”, powiedział{A?|a} {A}. „To ostatni dobry dzień do czwartku.”
„Parada”, powiedział{A?|a} {A}. „Niech ktoś załatwi paradę.”
== quip.good.tender
„Chodź tu, niech cię zobaczę”, powiedział{A?|a} {A} i {A?ujął|ujęła} twoją twarz w obie dłonie.
„Tak dobrze ci poszło”, powiedział{A?|a} {A}, i zawstydził{A?|a} się, że to powiedział{A?|a}.
„W puszce jest miód”, powiedział{A?|a} {A}. „Jest twój. Nie mów innym.”
== quip.good.stubborn
„{A?Mówiłem|Mówiłam}, że wytrzyma”, powiedział{A?|a} {A}, do nikogo w szczególności.
„To był mój plan”, powiedział{A?|a} {A}. „W większości.”
„Następnym razem od początku po mojemu”, powiedział{A?|a} {A} i wygrał{A?|a} spór, znikając, zanim padła odpowiedź.
== quip.bad.calm
„Jeden zły dzień to nie zły żywot”, powiedział{A?|a} {A} i, o ile ktokolwiek mógł ocenić, naprawdę tak myślał{A?|a}.
„Idziemy dalej”, powiedział{A?|a} {A}. „I tyle.”
„Siadaj, oddychaj, pomyślimy rano”, powiedział{A?|a} {A}.
== quip.bad.hot
„Gdybym tam {A?był|była}”, powiedział{A?|a} {A}, i zostawił{A?|a} to, a cisza dokończyła.
„Kto kazał iść lewą?”, {A?warknął|warknęła} {A}. „Kto im powiedział, że lewa jest bezpieczna?”
„Zabiję ich”, powiedział{A?|a} {A} bardzo cichym głosem.
== quip.bad.anxious
„A jeśli przyjdą tu następni?”, zapytał{A?|a} {A} i nikt nie chciał odpowiedzieć.
„Dziś w nocy lampy powinny być zgaszone”, powiedział{A?|a} {A}, po czym {A?obszedł|obeszła} dom i pogasił{A?|a} je wszystkie.
„Ilu brakuje?”, dopytywał{A?|a} {A}, choć odpowiedź się nie zmieniła.
== quip.bad.dry
„No cóż”, powiedział{A?|a} {A}, „poszło mniej więcej tak dobrze jak ostatnio.”
„Patrz na jasną stronę”, powiedział{A?|a} {A}. „Nie ma jej, ale patrz.”
„Nie dziękujcie mi wszyscy naraz”, powiedział{A?|a} {A}, stawiając miskę.
== quip.bad.tender
„Siadaj”, powiedział{A?|a} {A}, „siadaj, jedz, poczeka”, i {A?przesunął|przesunęła} miskę przez stół.
„To nie ty”, powiedział{A?|a} {A}. „To nie ty. To nie ty.”
„No chodź, położymy ci nogi wyżej”, powiedział{A?|a} {A}, jak do dziecka.
== quip.bad.stubborn
„Wracamy”, powiedział{A?|a} {A}. „Wracamy i nie przegrywamy dwa razy.”
„Chcę mieć plan na papierze do rana”, powiedział{A?|a} {A} i nie żartował{A?|a}.
„Nikt nie ma mówić, że to pech”, powiedział{A?|a} {A}. „To był błąd. Błędy można naprawić.”
== haul.title
{A} rozłożył{A?|a} to, co przyniesiono {map_from}
Posortowane według głodu: worek {map_from}
{A} przeczytał{A?|a} na głos łup {map_from}
{A} policzył{A?|a} to, co przyszło {place_from}
Rachunki po {map_loc}
{A} wypisał{A?|a} kredą łup na wieku skrzyni
Worek {map_from} leży na stole
Co się ostało {place_at}
{A} przeszukał{A?|a} kieszenie w łupie {map_from}
== haul.found
Worek {place_from} oddał {loot_list}.
{place2_from} przyniesiono {loot_list}, znalezione pod zawaloną półką i niesione do domu przy piersi.
Przyniesiono {loot_list} — tyle zostało {place_at}, a kurz na tym mówił, że czekało to długo.
Przyniesiono {loot_list}, wszystko {place_from}, nadal pachnące pomieszczeniem, z którego pochodziło.
{map_from} przyniesiono łup — {loot_list}. Większość {place_from}, a {A} już powiedział{A?|a}, dla kogo to jest.
{place_from}, w podartej zasłonie, przyniesiono {loot_list}.
Przyniesiono {loot_list}. Leżało {place_at}, pod łóżkiem, za luźną deską: w takim miejscu znajdzie tylko cierpliwy.
{A} przeliczył{A?|a} na stole łup {map_from} — {loot_list} — a wszyscy patrzyli na rachunek z lekko otwartymi ustami.
== haul.food
{A} obracał{A?|a} puszkę w świetle, potrząsał{A?|a} nią przy uchu i napisał{A?|a} na wieczku modlitwę woskowym ołówkiem.
Puszki od razu poszły do garnka, a {A} pierwszą chochlę dał{A?|a} do najmniejszej miski.
{A} otworzył{A?|a} pierwszą puszkę na miejscu i pozwolił{A?|a} każdemu powąchać, tak dla samej zasady.
{A} powiedział{A?|a}, że puszki wykarmią wszystkich {camp_at} na dwa wieczory, jeśli nikt nie poprosi o dokładkę, a wszyscy poprosili o dokładkę.
{A} poukładał{A?|a} puszki według etykiet, a te bez etykiet pośrodku, jako niespodziankę na przyszłość.
{A} oblizał{A?|a} kciuk, spróbował{A?|a} sosu z wgniecionej puszki i poważnie pokiwał{A?|a} głową.
== haul.med
{A} przeliczył{A?|a} opatrunki do szafki jeden po jednym, a antybiotyki {A?zamknął|zamknęła} w blaszanej skrzynce z kluczem na szyi.
{A} rozłożył{A?|a} lekarstwa przy lampie jak karty i długo na nie patrzył{A?|a}, zanim wybrał{A?|a}, co wydać.
{A} dwa razy przeczytał{A?|a} etykiety i powiedział{A?|a}, że daty są optymistyczne, ale optymizm to też rodzaj leku.
{A} {A?wyjął|wyjęła} spirytus z torby i odstawił{A?|a} go od pieca, a potem także od kucharzy.
{A} {A?owinął|owinęła} każdy bandaż w czystą szmatkę, żeby starczył na dłużej.
== haul.ammo
{A} rozsypał{A?|a} naboje w papierowe zwitki po pięć i zapisał{A?|a} ołówkiem liczby.
{A} wsypał{A?|a} naboje do puszki po kawie, a ich grzechot był małą muzyką.
{A} podzielił{A?|a} amunicję na trzy torby, żeby jeden błąd nie kosztował wszystkiego.
{A} {A?uniósł|uniosła} nabój do lampy, obracał{A?|a} go między palcami i powiedział{A?|a}, że to kolejny spór rozstrzygnięty.
{A} wycierał{A?|a} każdy nabój o rękaw, zanim trafił do puszki, jakby kurz mógł mu zaszkodzić.
{A} schował{A?|a} amunicję do skrzyni pod schodami i przez minutę stał{A?|a} na wieku, myśląc.
== haul.tool
{A} obracał{A?|a} znalezisko w świetle, powiedział{A?|a}, do czego służy, i {A?zaczął|zaczęła} listę rzeczy do naprawienia.
{A} {A?zdmuchnął|zdmuchnęła} z niego kurz, sprawdził{A?|a} ostrze kciukiem i nie {A?mógł|mogła} przestać się uśmiechać.
{A} {A?zawinął|zawinęła} znalezisko w szmatę i {A?zaniósł|zaniosła} je jak kota do warsztatu.
{A} {A?uniósł|uniosła} to, żeby wszyscy widzieli, a dzieci zrobiły z tego kapelusz.
{A} naoliwił{A?|a} to na miejscu, co jest formą czci.
== keep.chess
Pod spodem leżała szachownica {place_from}, bez czarnego skoczka, którego zastępował kapsel od butelki.
Szachownica złożona na pół, z kółkiem po kawie na polu białej królowej.
Szachownica {place_from} była ostatnią rzeczą wyjętą z worka i pierwszą, którą zauważyły dzieci.
== keep.guitar
Na dnie leżała zwinięta struna gitarowa, srebrna i okrutna, pachnąca wnętrzem {place_gen}.
Pojedyncza struna gitarowa, nawinięta na ołówek, {place_from}.
== keep.comic
Komiks {place_from}, wilgotny przy grzbiecie, z wyrwaną ostatnią stroną i plotką o tym, jakie było zakończenie.
Komiks z zamaskowanym mężczyzną na okładce, z rozmiękłym w rogach tuszem.
== keep.teddy
Twarzą w dół na dnie leżał pluszowy miś {place_from}, z jednym okiem i zapachem cudzej sypialni.
Pluszowy miś, trochę spleśniały, z guzikiem tam, gdzie powinno być oko.
== keep.seeds
Woreczek nasion {place_from}, podpisany starannym pismem: pomidor, i rok dawno miniony.
Mały papierowy woreczek z nasionami, z odręcznie narysowanym pomidorem na przodzie, złożony do rozmiaru kciuka.
== keep.cards
Talia kart w gumce {place_from}, bez siódemki trefl.
Talia kart, miękka jak szmata, z kółkiem po kawie na asie kier.
== keep.harmonica
Harmonijka {place_from}, zmatowiała, z wgnieceniem w osłonie i jedną nutą, która wciąż brzmiała, gdy ktoś dmuchnął.
Harmonijka w skarpecie, a gdy dzieci spróbowały, jedna blaszka zaśpiewała.
== haul.keep
{B} upomniał{B?|a} się o {kitem_a_acc} dla dzieci, zanim zamknięto worek, i nikt nie protestował.
{A} położył{A?|a} {kitem_a_acc} na półce nad piecem, gdzie każdy może zobaczyć i nikt nie może udawać, że tego nie widzi.
{kitem_a_acc} podawano z rąk do rąk, aż to wylądowało na kolanach najmłodszego, który nie chciał puścić.
{A} postawił{A?|a} {kitem_a_acc} na stole i powiedział{A?|a}, że dzień jest już lepszy.
{B} powiedział{B?|a}, że {kitem_a} przyda się na długie noce, i tak to zabrzmiało, jak obietnica.
"""
