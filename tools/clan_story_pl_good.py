"""Polish clan feed lines, part 1 (parallel to tools/clan_story_lines_good.py: the same kinds, the same order, the same scopes; only the text).

Template syntax (tools/clan_story_pl.py renders it):
  {A} {B} {C} {D}        the name, never declined (the names are names: the lines are phrased in the nominative)
  {A?m|f}                gender switch: masculine form | feminine form (neutral names take the masculine one), e.g. znalaz{A?ł|ła}
  {AB?li|ły}             the same for two people: the feminine form only when ALL of them are female (virile plural otherwise)
  {place} {place_gen} {place_at} {place_to} {place_from}     the faction's place in the nominative / genitive / "na stadionie" / "na stadion" / "ze stadionu"
  {enemy} {enemy_gen} {enemy_ins}    Blizny / Wilki in the cases;  {inf} {inf_gen} {inf_ins} {infs} {infs_gen} {inf_two}   the infected
  {ill} {ill_gen} {ill_acc} {ill_ins}  and {cure} {cure_gen} {cure_acc} {cure_ins}   the illness / the medicine in the cases
  {n} {n_acc} {n_gen} {n_cnt}  {lost} ... {gain} ...   counts of people (nom / acc / gen / the bare numeral); {ago} {day} {week}
"""

LINES = {}

LINES["hope"] = [
    "{A} znalaz{A?ł|ła} w zawalonym domu stos starych książek. Dziś wieczorem ustawia się kolejka, żeby usłyszeć pierwszy rozdział na głos.",
    "{B} gwiżdże teraz na dwa palce, a winowajcą jest {A}. Cierpi na tym cały obóz.",
    "Po burzy pojawiła się tęcza. {A} wyciągn{A?ął|ęła} wszystkich, żeby ją zobaczyli. Nawet {B} podni{B?ósł|osła} wzrok.",
    "{A} naprawi{A?ł|ła} wszystkim buty. Suche stopy. Nie wiesz, jak bardzo ich brakuje, dopóki nie wrócą.",
    "Dziś rano na każdym posłaniu leżał kwiat. Nikt się nie przyznaje. Wszyscy się uśmiechają.",
    "Kłótnia o to, jak najlepiej przyprawić królika: {A} kontra {B}. Szczerze mówiąc, najlepsza kłótnia od miesięcy.",
    "{A} znalaz{A?ł|ła} grę planszową bez połowy pionków. Wymyśliliśmy nowe zasady. {B} sromotnie przegra{B?ł|ła} i {B?przysiągł|przysięgła} zemstę.",
    "Pod murem przeszło ubiegłej nocy {inf_two} i poszło dalej. Cisza. {A} stwierdzi{A?ł|ła}, że to dobry znak. Powiedzia{A?ł|ła} to dwa razy.",
    "Kanapa wylądowała na dziedzińcu i płonie ognisko. Sprawcy: {A} i {B}. Połowa obozu siedziała po północy i po prostu gadała. Zwykły wieczór, choć raz.",
    "Ktoś znalazł {place_at} gitarę, a {A} naprawdę zna trzy akordy. Brzmi okropnie. Nikt nie chce, żeby {A?przestał|przestała}.",
    "{A} uruchomi{A?ł|ła} stare radio. Szum i godzina muzyki Bóg wie skąd, a my staliśmy jak idioci. Piękne.",
    "Dzieciaki ganiały się dziś wokół {place_gen}, śmiejąc się, i nikt nie kazał im być cicho. Zapomnieliśmy, jak brzmi taki śmiech.",
    "{A} ma pomidory. Prawdziwe, już dojrzewają. {A?On|Ona} nikogo do nich nie dopuszcza, ale wszyscy jesteśmy cholernie dumni.",
    "Dziś rano przybłąkał się pies, chudy, ale piekielnie przyjazny. {A} nazwa{A?ł|ła} go Ciastkiem, zanim ktokolwiek zdążył zagłosować. Zostaje z nami.",
    "{B} ma dziś urodziny. Nikt nie pamięta, ile {B} ma lat, więc stanęło na trzydziestu. {A} upiek{A?ł|ła} coś z mąki kukurydzianej i prawie wyszło ciasto.",
    "Pełne brzuchy, cicha noc i ani jednego {inf_gen} pod płotem. Biorę to. Dzień {day}, a my wciąż tu jesteśmy.",
    "{A} i {B} uczą dzieciaki grać w karty przy piecu. {B} oszukuje. Dzieciaki wiedzą. Nikogo to nie obchodzi.",
    "Wieczór był na tyle ładny, że jedliśmy na dworze. {A} wymieni{A?ł|ła} scyzoryk na słoik miodu, który obszedł cały stół.",
    "{A} rozwiesi{A?ł|ła} lampki na starych akumulatorach samochodowych wzdłuż {place_gen}. Połowa mruga, ale całe miejsce wygląda jak coś, czego warto bronić.",
    "Dziś rano {A} nuci{A?ł|ła} przy czyszczeniu karabinów. Od tygodni tego nie słyszeliśmy. Może jednak coś się poprawia.",
    "{B} skończy{B?ł|ła} dach od wschodniej strony. Pierwsza noc bez wiadra pod przeciekiem. Drobiazgi, Jezu, drobiazgi.",
    "Dziś oglądaliśmy wschód słońca {place_from}. Nikt nie mówił wiele. {A} rzuci{A?ł|ła} tylko: „Kolejny dzień za nami”, i to wystarczyło.",
    "{A} śpiewa{A?ł|ła} dziś przy ognisku starą pieśń z dawnych czasów. Cały obóz ucichł, a przy drugiej zwrotce dołączył. Jej Światło było z nami.",
    "Dzieci bawiły się na brzegu, aż światło zgasło, i nikt ich nie wołał do domu. Prorokini by się uśmiechnęła.",
    "{A} zasadzi{A?ł|ła} pierwszy rząd fasoli w nowym ogrodzie. Ziemia jest tu łaskawa. Mamy nadzieję na ten sezon.",
    "{B} wystruga{B?ł|ła} każdemu maluchowi małego ptaszka. {A} twierdzi, że kolejność dziobania jest już negocjowana.",
    "Dziś przy długim stole dzieliliśmy się chlebem i miodem. {A} wypowiedzia{A?ł|ła} błogosławieństwo, a {B} śmia{B?ł|ła} się przez cały czas.",
    "{A} wróci{A?ł|ła} znad brzegu z bezpańskim psem u nogi. Starsi mówią, że nie wykarmimy kolejnej gęby. {A} i tak go nakarmi{A?ł|ła}.",
    "{A} i {B} napraw{AB?ili|iły} stare krosno i tkalnia znów jest pełna dźwięków. Jak dawniej.",
    "{A?Brat|Siostra} {A} złowi{A?ł|ła} więcej ryb, niż pomieściły sieci. Połowę uwędziliśmy. Dziś ucztujemy, jutro odpoczywamy.",
    "{A} zapali{A?ł|ła} wieczorne lampy olejem ze słonecznika. Cały obóz rozbłysnął. Jej Światło także w drobiazgach.",
    "Pierwszy raz od tygodni nikt dziś wieczorem nie modlił się o jedzenie. Modliliśmy się w podzięce.",
    "{A} nauczy{A?ł|ła} najmłodszych starych wyliczanek. Rozbrzmiewają one teraz {place_at}. To najpiękniejszy dźwięk, jaki mamy.",
    "{B} skończy{B?ł|ła} nowy dach na długim domu. Spadł deszcz i ani jedna kropla nie wpadła do środka. Podziękowaliśmy, a {B} się ukłoni{B?ł|ła}.",
]

LINES["plenty"] = [
    "{A} dwa razy przeliczy{A?ł|ła} zapasy. Mamy więcej, niż potrzeba. Dwa razy.",
    "Dziś pełne garnki. Nikt nie zostawił nic w misce i nikt nie zmarnował ani kęsa. Nadzieja smakuje tak dobrze jak to jedzenie.",
    "Wyprawa po zaopatrzenie wróciła z ciężkimi plecakami. Fasola z puszki, mąka, nawet trochę cukru. {B} zatańczy{B?ł|ła} i nikt nigdy o tym nie wspomni.",
    "Jedliśmy, aż nie dało się więcej. Pierwszy raz od dawna. {A} zasn{A?ął|ęła} przy stole.",
    "Jest nadwyżka, prawdziwa. {B} już kombinuje, jak ją rozciągnąć na zimę.",
    "{A} upiek{A?ł|ła} prawdziwy chleb. Ze skórką i w ogóle. Można się było prawie rozpłakać.",
    "Na półkach w spiżarni znów są luki, bo zapasy przesunęły się do przodu. Luki między stosami, nie tam, gdzie kiedyś było jedzenie.",
    "Dokładki! Dziś były dokładki. {A} wzi{A?ął|ęła} dwie.",
    "Cholerna uczta dziś wieczorem. {A} wymieni{A?ł|ła} zestawy do czyszczenia karabinów na całą szynkę. Isaac może sobie zatrzymać swoje racje.",
    "Zapasy rosną, {place_at} jest spokojnie, a wszyscy mają pełne brzuchy. Po raz pierwszy jedyne skargi dotyczą chrapania.",
    "Mamy więcej jedzenia, niż trzeba. {B} mówi, że to dobry problem. Ja mówię, że cud.",
    "{A} trafi{A?ł|ła} w jackpot na wyprawie: zamknięte skrzynie, suchy prowiant, przyprawy. Przyprawy! Dosoliliśmy wszystko.",
    "Kuchnia {place_gen} pęka w szwach. {B} rozdawa{B?ł|ła} dokładki i zmiana wartowników po raz pierwszy ma dobry humor.",
    "Pełne żołądki, pełne magazynki i czysta noc. Nieźle jak na koniec świata.",
    "Patrzcie na to. Cała półka puszek, wszystkie nasze. {A} wciąż ich dotyka, jakby miały zniknąć. Cholera, mogą.",
    "Spichlerz jest pełny. Starsi ogłosili dzień dziękczynienia. {A} poprowadzi{A?ł|ła} błogosławieństwo, a {B} taniec.",
    "Morze było hojne. Sieci wróciły ciężkie, a ogniska paliły się cały wieczór. Prorokini zapewnia.",
    "Mamy dość, i więcej. Maluchy jadły, aż im twarze błyszczały, i nikt ich nie zbeształ.",
    "{A} upiek{A?ł|ła} słodki chleb z miodem. Zapach poniósł się po całej wyspie i ludzie schodzili się ze wszystkich stron.",
    "Żniwa zebrane. Mamy w bród, a Starsi proszą, byśmy pamiętali, jak było, gdy nie mieliśmy.",
    "Pełne brzuchy, lekkie serca. To rzadkość. {A} śpiewa{A?ł|ła}, aż wyszły gwiazdy.",
    "{B} otworzy{B?ł|ła} ostatnią beczkę suszonych jabłek i rozdaliśmy je wszystkim. Słodkie, ciągnące się, nikt nie chciał skończyć pierwszy.",
]

LINES["calm"] = [
    "Dziś nic się nie wydarzyło. Najlepsza wiadomość od dawna.",
    "Spokojny dzień. {A} {A?zamiótł|zamiotła} podłogę, {B} załata{B?ł|ła} ścianę. To cały raport.",
    "Deszcz bębnił w dach przez całe popołudnie. {A} mówi, że to dobre dla ogrodu. {B} mówi, że dobre do spania.",
    "{A} i {B} opowiada{AB?li|ły} sobie, co rob{AB?ili|iły} przedtem. Pewnie głównie kłamstwa. Dobre kłamstwa.",
    "Przeliczyliśmy zapasy, sprawdziliśmy grafik wart, załataliśmy, co trzeba. Dzień {day}. Tak samo jak wczoraj, i mówię to jako pochwałę.",
    "{A} próbuje nauczyć nowych struganiu. Nowi są okropni. {A} jest cierpliw{A?y|a}.",
    "Wiatr zmienił kierunek i dym poszedł w drugą stronę. Przez godzinę nikt nie kasłał. Nazywamy to dobrym dniem.",
    "Nocna warta była nudna. Kocham każdą minutę tej nudy.",
    "Dziś cicho {place_at}. Żadnych Blizn, żadnych zarażonych, żadnych alarmów. Biorę nudę.",
    "{A} wyczyści{A?ł|ła} broń, {B} zrobi{B?ł|ła} spis amunicji, a ja ucinam sobie drzemkę. Nic do zgłoszenia. Dzień {day}.",
    "Radio milczało. To albo bardzo dobrze, albo bardzo źle. Wybieram dobrze.",
    "Kolejny dzień, kolejny patrol. {A} mówi, że przeszliśmy każdy cal tej dzielnicy. Ja mówię, że jutro przejdziemy jeszcze raz.",
    "Światła zamigotały, ale wytrzymały. {B} mówi, że agregat da radę jeszcze tydzień. Tydzień to dużo w dzisiejszych czasach.",
    "Szare niebo, zimny wiatr i nic się nie dzieje. Isaac nazwałby to dyscypliną. Ja nazywam to wtorkiem.",
    "Stoję na warcie, a obok stoi {A}. Żartujemy o tym, jak ubierają się Blizny. Niemiłe, ale pomaga.",
    "Kolejny dzień na wyspie. Odpływ, przypływ. {A} naprawia{A?ł|ła} sieci, {B} zbiera{B?ł|ła} wodorosty.",
    "Cichy poranek. Starsi poprowadzili modlitwę o świcie, a dzieci siedziały ze złożonymi rękami, prawie nieruchomo.",
    "Łaska Prorokini kryje się w drobiazgach: suchy koc, ciepły kubek, {A} nucąc{A?y|a} cicho pod nosem.",
    "Rzeźbiliśmy, tkaliśmy, jedliśmy. Nie mamy nic do zgłoszenia poza oddechem, i za to jesteśmy wdzięczni.",
    "Dziś wiał lekki wiatr. {A} mówi, że to znak. {B} mówi, że to tylko wiatr.",
    "Wyspa jest cicha. Straż czuwa. Śpimy trochę spokojniej.",
    "{A} i {B} siedzi{AB?eli|ały} na pomoście i patrz{AB?yli|yły}, jak nadciąga mgła. Nie było o czym mówić i nie trzeba było.",
]

LINES["join"] = [
    "{A} {A?przywlókł|przywlekła} się dziś rano, na wpół zagłodzon{A?y|a} i cał{A?y|a} w kurzu. {B} dał{B?|a} {A?mu|jej} miskę zupy i koc.",
    "Ktoś nowy zjawił się przy bramie. {A}. Mówi, że słyszał{A?|a}, że mamy jedzenie. Mamy, ledwo. Zostaje z nami.",
    "{A} do nas dołączy{A?ł|ła}. {A?Dobry strzelec, lepszy kucharz|Dobra strzelczyni, jeszcze lepsza kucharka}. {B} mówi, że świetnie się tu odnajdzie.",
    "{A} spa{A?ł|ła} w progu przy drodze, kiedy {A?go|ją} znaleźliśmy. {B} {B?niósł|niosła} {A?go|ją} resztę drogi. Teraz jest już na nogach, je i zadaje pytania.",
    "Nowa twarz. {A}. Dość małomówn{A?y|a}. {B} pokaza{B?ł|ła} {A?mu|jej} prycze. Zobaczymy, czy zostanie.",
    "{A} mówi, że od miesięcy był{A?|a} sam{A?|a}. Dziś ma łóżko, miskę i coś na kształt rodziny.",
    "{A} {A?wszedł|weszła} do obozu z psem, kulejąc. Zatrzymaliśmy psa. {A?Jego|Ją} też.",
    "Nowy rekrut {place_at}. {A}. Bystr{A?y|a}, wystraszon{A?y|a} i dobr{A?y|a} z karabinem. Witamy w tym bajzlu.",
    "{A} {A?przyszedł|przyszła} z drogi, błagając o robotę. {B} wpisa{B?ł|ła} {A?go|ją} na grafik wart, zanim {A?zdążył|zdążyła} odmówić.",
    "{A} nie by{A?ł|ła} po niczyjej stronie, chciał{A?|a} tylko dachu nad głową. Dostał{A?|a} go. Isaac będzie narzekał, ale on narzeka na wszystko.",
    "{A} zjawi{A?ł|ła} się przy punkcie kontrolnym z samą manierką i imieniem. {B} poręczy{B?ł|ła} za {A?niego|nią}. Dla mnie to wystarczy.",
    "{A} {A?przypłynął|przypłynęła} dziś wieczorem przez wodę i poprosi{A?ł|ła} o schronienie. Starsi się zgodzili.",
    "Na przystani pojawi{A?ł|ła} się {A?obcy|obca}, a {B} {B?powitał|powitała} {A?go|ją}. {A} mówi, że o naszej wyspie słyszał{A?|a} od podróżnika.",
    "{A} poprosi{A?ł|ła} u bramy o przyjęcie. Obmyliśmy {A?go|ją} i daliśmy {A?mu|jej} łóżko. Rodzina Prorokini rośnie.",
    "{A} jest now{A?y|a} na naszym brzegu. Cich{A?y|a}, głodn{A?y|a}, ale chętn{A?y|a} do pracy. {B} posadzi{B?ł|ła} {A?go|ją} przy sieciach.",
    "Kolejna dusza nas odnalazła. {A} ma ręce cieśli, mówią Starsi. Zobaczymy.",
]

LINES["recovery"] = [
    "{A}: gorączka spadła dziś rano. {A?On|Ona} poprosi{A?ł|ła} o grzankę. Nie mamy grzanek, ale już samo to, że prosi{A?ł|ła}, coś znaczy.",
    "{A} znów stoi na nogach. {B} mówi, że {A?miał|miała} szczęście. {A} mówi, że {B} {B?był|była} dobr{B?y|a}.",
    "{A} usiad{A?ł|ła} i powiedzia{A?ł|ła}: „Jestem głodn{A?y|a}”. Najlepsze słowa, jakie usłyszeliśmy w tym tygodniu.",
    "Kaszel minął. {A} dokończ{A?ył|yła} lekarstwo, które znalazł{B?|a} {B}, i teraz chodzi i opowiada wszystkim, jak dzielnie się trzymał{A?|a}.",
    "{A} z tego wyjdzie. Było blisko, ale {A} z tego wyjdzie. Potrzebowaliśmy tego.",
    "Całą noc przy łóżku czuwa{B?ł|ła} {B}, a o świcie {A} odzyska{A?ł|ła} kolory na twarzy. Nikt nie mówi: cud, ale nikt nie mówi, że to nie cud.",
    "{A} {A?obszedł|obeszła} dziś teren po raz pierwszy od zachorowania. Powoli, ale pewnie.",
    "{A} wyzdrowia{A?ł|ła}. Nikt nie wie dokładnie dlaczego i nikt nie zamierza zadawać zbyt wielu pytań.",
    "Z {ill_gen} {A} {A?wyszedł|wyszła} cało, dzięki Bogu. {B} mówi, że to lekarstwa, które zdobyliśmy w ruinach.",
    "{A} wróci{A?ł|ła} na grafik wart, wciąż blad{A?y|a}. Mówi, że miło być {A?potrzebnym|potrzebną}. Ja mówię, że miło po prostu żyć.",
    "Lekarstwo zadziałało. {A} wstał{A?|a} i przeklina piec, czyli jest już w normie.",
    "{A} {A?wyszedł|wyszła} z tego. Kurwa, było blisko. Nie strasz nas więcej.",
    "Medyk mówi, że {A} z tego wyjdzie. Płuca czyste, gorączka minęła. Dobra wiadomość, choć raz, {place_at}.",
    "{A} zatrzyma{A?ł|ła} dziś w żołądku cały posiłek. Brzmi jak nic. To wszystko.",
    "Z posłania, na którym leży {A}, nie dochodzi już kaszel. Wszyscy spali lepiej.",
    "{A} wsta{A?ł|ła} z łóżka. Uzdrowicielka mówi, że najgorsze minęło. Dziękujemy Prorokini i ziołom.",
    "O świcie gorączka spadła. {A} usiad{A?ł|ła}, uśmiechn{A?ął|ęła} się i poprosi{A?ł|ła} o wodę. Płakaliśmy otwarcie.",
    "{A} dochodzi do siebie. Leki uzdrowicielki, modlitwy, a przy łóżku czuwa{B?ł|ła} {B}. Jakoś to wystarczyło.",
    "Jej Światło było łaskawe. {A} wyzdrowia{A?ł|ła} i znów chodzi po brzegu.",
    "Długą noc czuwa{B?ł|ła} {B}, aż wreszcie {A} {A?zaczął|zaczęła} oddychać spokojniej. Dziś śpiewamy.",
    "{A} jest zdrow{A?y|a}. Maluchy przyniosły {A?mu|jej} koronę z wodorostów, a {A} nosi{A?ł|ła} ją z wielką godnością.",
    "{A}: baliśmy się o {A?jego|jej} życie, ale {A?wrócił|wróciła} do nas. Uzdrowicielka mówi, że to dar, i jesteśmy wdzięczni.",
]

LINES["event_hold"] = [
    "Wytrzymaliśmy. Naprawdę wytrzymaliśmy. Straty: {lost}. To o wiele za dużo, ale obóz stoi i większość z nas też.",
    "{A} twierdzi, że różnicę zrobiło szkolenie. Straciliśmy {lost_acc}, ale mogliśmy stracić wszystkich.",
    "{enemy} rozbiły się o barykadę i uciekły. To kosztowało nas {lost_acc}. Niech będzie.",
    "Gdy strzały ucichły, a dym opadł, {B} wciąż stał{B?|a} przy bramie. Tak jak większość obozu.",
    "{A} i {B} przyję{AB?li|ły} pierwszą falę i utrzyma{AB?li|ły} linię. Straciliśmy {lost_acc}, ale reszta z nas żyje i może o tym opowiadać.",
    "Ćwiczyliśmy całymi dniami i to zadziałało. {enemy} wycofały się z podkulonymi ogonami.",
    "Blizny uderzyły w nas wszystkim, co miały, a my wytrzymaliśmy. Straciliśmy {lost_acc}, ale oni więcej. Isaac będzie chciał o tym usłyszeć.",
    "{A} nauczy{A?ł|ła} pół obozu, jak się wycofywać w porządku. Uratowa{A?ł|ła} co najmniej tuzin żyć. Straciliśmy {lost_acc}, ale to zwycięstwo.",
    "Utrzymaliśmy linię {place_at}. Kurwa, utrzymaliśmy. Blizny odchodzą kulejąc, a my wciąż stoimy.",
    "Dziś przetrzepaliśmy Blizny do krwi. Straciliśmy {lost_acc}, ale chyba prędko nie spróbują ponownie.",
    "Szkolenie się opłaciło. Blizny wpadły gorące, a wyszły w kawałkach. Kosztowało nas {lost_acc}; opłaczemy ich jutro. Dziś jemy.",
    "Blizny rozbiły się o nasze lufy. {B} mówi, że to najlepsza obrona, jaką w życiu widzia{B?ł|ła}. Straciliśmy {lost_acc}, ale wytrzymaliśmy.",
    "Wilki rozbiły się o nasze mury. Straciliśmy {lost_acc}, ale wyspa stoi. Prorokini nad nami czuwała.",
    "Obroniliśmy brzeg. Wśród wiernych strata: {lost}, ale Wilków też już nie ma. Jej Światło i nasze dzięki.",
    "{A} dowodzi{A?ł|ła} łucznikami z dachu, a {B} trzyma{B?ł|ła} bramę. Straciliśmy {lost_acc}, to łaska wobec tego, co mogło się stać.",
    "Wilki odparto. Straciliśmy {lost_acc}, a maluchy są bezpieczne w piwnicy. To jedyne zwycięstwo, które się liczy.",
    "Szkolenie się sprawdziło i Wilki uciekły. Straciliśmy {lost_acc}, a w naszych pieśniach będziemy ich nieść.",
    "Prorokini dziś się do nas uśmiechnęła. Wilki uciekły, straciliśmy {lost_acc}, a mury wciąż stoją.",
]

LINES["event_growth"] = [
    "Dziś przyjęliśmy {gain_acc}. {A} już opowiada historie, a {B} już robi miejsce.",
    "Przed bramą zjawiła się grupa, głodna i zmęczona, ale chętna do pracy. Przybyło nam {gain_gen}: tyle nowych gęb i tyle samo par rąk.",
    "Ochroniliśmy ich i teraz są nasi. Przybyło {gain_gen}, wśród nich {A}. Dobrze widzieć, jak to miejsce się zapełnia.",
    "{A} dołączy{A?ł|ła} z uporem wartym całej rodziny. Razem przybyło {gain_gen}, a obóz wydaje się większy.",
    "Przyjaźni ocalali zostali z nami: {gain}, na czele {A}. {B} już pokazuje im, jak tu wszystko działa.",
    "Z zimna przybyli ocaleni: {gain}. {A} rozpłaka{A?ł|ła} się na widok ognia. Wszyscy udawaliśmy, że nie widzimy.",
    "Nowy nabór {place_at}: {gain}, a {A} pierwsz{A?y|a} w kolejce. Isaac mówi, że to wygrana. Ja mówię, że to masa łóżek do znalezienia.",
    "Z tej akcji mamy {gain_acc}. {A} był{A?|a} kiedyś {A?medykiem|medyczką}, dzięki Bogu. {B} jest zachwycon{B?y|a}.",
    "Uratowaliśmy {gain_acc}. {A} {A?był jednym z nich|była jedną z nich}. To nie jest bezpieczne miejsce, ale bezpieczniejsze niż to, skąd przyszli.",
    "Świeża krew: {gain}. {A} już umie strzelać i ma opinię o naszych racjach.",
    "Chryste, ale tłum: {gain}. {B} oprowadza. {A} wciąż pyta o prysznice. Nie mamy żadnych.",
    "Przybyli do nas nowi bracia i siostry: {gain}. {A?Pierwszy ukląkł|Pierwsza uklękła} przy ogniu {A}.",
    "Prorokini zesłała nam {gain_acc}. {A} mówi, że {A?szedł|szła} za naszym dymem całymi dniami. Witajcie, witajcie.",
    "Na nasz brzeg przybyli obcy: {gain}. {A} odezwa{A?ł|ła} się pierwsz{A?y|a}, dziękując za łódź. Podzieliliśmy się chlebem.",
    "Wyrwaliśmy z rąk Wilków {gain_acc}, wśród nich {A}. Na wyspie jest dziś więcej głosów.",
    "{A} przeprawi{A?ł|ła} przez wodę jeszcze {gain_acc}. Są chudzi, ale chętni. Starsi dali im koce.",
    "Wspólnota rośnie o {gain_acc}. {A} dołączy do tkalni, a {B} zajmie się resztą. Niech Jej Światło ich osłania.",
]

LINES["founding"] = [
    "Pięcioro z nas dotarło {place_to}: {A}, {B}, {C} i jeszcze dwoje. Mamy jedzenie na kilka dni i mnóstwo nadziei.",
    "Dwanaście tygodni. Taki jest plan. {A} napisa{A?ł|ła} tę liczbę na ścianie, żebyśmy nie zapomnieli.",
    "{A} rozpali{A?ł|ła} dziś {place_at} pierwsze ognisko. {B} stwierdzi{B?ł|ła}, że to zły pomysł. {B} i tak został{B?|a}.",
    "Dzień pierwszy {place_at}. Pięcioro nas, trochę fasoli i karabin, który w większości działa. Isaac mówi: trzymać pozycję. Utrzymamy.",
    "Nowy start, nowe prycze, nowe problemy. {A}, {B}, {C}. Jeśli będziemy ostrożni, może nawet przetrwamy zimę.",
    "Dotarliśmy na wyspę o zmierzchu: {A}, {B}, {C} i dwoje innych. Światło Prorokini wyszło nam na spotkanie.",
    "Nowy początek {place_at}. Starsi pobłogosławili naszą piątkę i dali nam chleb. Okażemy się godni.",
    "Pięcioro nas stoi na brzegu: {A}, {B}, {C}. Razem rozpaliliśmy to ognisko. Niech płonie dwanaście tygodni.",
]

LINES["clan_won"] = [
    "Dwanaście tygodni. Udało się. Naprawdę się udało. {A} płakał{A?|a}, {B} wiwatował{B?|a}, a reszta stała z otwartymi ustami.",
    "Ostatni dzień minął jak każdy inny, a potem było po wszystkim. Żyjemy. Wielu z nas, w każdym razie.",
    "Przetrwaliśmy. To nie wydaje się prawdziwe. {A} co chwilę się szczypie.",
    "Straciliśmy ludzi i będę to nosić w sobie. Ale ci, którzy zostali, są najsilniejsi, jakich znam.",
    "Dwanaście tygodni, a klan wciąż stoi. Isaac może o nas mówić, co chce. Przetrwaliśmy dłużej niż Blizny, głód, wszystko.",
    "Dzień osiemdziesiąty trzeci. Zapaliliśmy wszystkie lampy {place_at} i zaśpiewaliśmy coś głupiego. Najlepsza noc w moim życiu.",
    "Udało się. Kurwa, udało się. {A} jest pijan{A?y|a}, {B} tańczy i nikt nie ma siły ich powstrzymywać.",
    "Przetrwaliśmy. To jest to słowo. Nie „wygraliśmy”, nie „pokonaliśmy”. Przetrwaliśmy. I to wystarczy.",
    "Minęło dwanaście tygodni, a my wciąż tu jesteśmy. Prorokini szła z nami przez całą drogę.",
    "Starsi mówią, że jesteśmy błogosławieni. Ja mówię, że uparci. Może to to samo.",
    "Przeżyliśmy. Wyspa jest nasza na kolejny sezon, a Jej Światło jest ciepłe.",
    "Śpiewaliśmy całą noc. {A} prowadzi{A?ł|ła} pieśni, {B} bębni{B?ł|ła} w wiadro, a Wilki mogłyby przyjść i nawet byśmy tego nie zauważyli.",
]


# The rich good-state ticker lines live next to their English originals in clan_story_good_rich.py (the registry in clan_story_pl.py
# builds them as pool "t:g"); this is the Polish half of those rows, in the same order, for anyone reading the Polish files.
import clan_story_good_rich as _RG
RICH_PL = [pl for _scope, _en, pl in _RG.ROWS]
