"""Polish clan saga templates, part 4: line for line parallel to clan_saga_text4.py (extra variety and the tails).  See clan_saga_pl.py for the rules."""
TEXT = r"""
== haul.found
{place_at} już dwa razy wszystko przetrząsano, ale {A} wiedział{A?|a}, gdzie szukać, i przyniesiono {loot_list}.
Na dnie szuflady {place_gen} znaleziono {loot_list}.
Za fałszywą ścianą {place2_gen}, ukryte przez kogoś, kto nigdy po to nie wrócił, znaleziono {loot_list}.
Łup {map_from} w kolejności znajdowania — {loot_list}. Ostatnia rzecz pochodziła {place_from} i {A} potrafi opisać to pomieszczenie.
Do domu niesiono w poszewce {place_from} {loot_list}.
Wyniesiono {loot_list}. To cały łup {map_from}, a każda rzecz ma swoją historię, głównie o {place_loc}.
{place2_from} wydobyto ostatni sekret: {loot_list}.
Wśród ruin {place_gen}, w zalutowanej puszce, którą otwierały trzy osoby, znaleziono {loot_list}.
Przyniesiono {loot_list}. Wszystko {place_from}, oprócz tego jednego, o czym nie chce się mówić.
Pod zawalonym sufitem {place_gen} była torba, której nikt nie ruszał. Wyjęto z niej {loot_list}.
Po to trzeba było się czołgać {place2_at}, ale na stół wyłożono {loot_list}.
Znaleziono {loot_list}. Leżało na widoku {place_at}, dlatego nikt inny tego nie podniósł.
== haul.keep
Na końcu z worka wyjęto {kitem_a_acc}, a każda ręka w pokoju sięgnęła po to.
{B} powiedział{B?|a}, że {kitem_a} nikomu się nie przyda, a potem zabrał{B?|a} to do łóżka.
{kitem_a} trafi na długą półkę, powiedział{A?|a} {A}, a długa półka to miejsce na dobre rzeczy.
Dzieci zobaczyły {kitem_a_acc} i zamilkły, co jest u nich najwyższą pochwałą.
{A} dwa razy obrócił{A?|a} {kitem_a_acc}, odłożył{A?|a} to i znów {A?podniósł|podniosła}.
{B} patrzył{B?|a} na {kitem_a_acc} tak, jak inni patrzą na wschód słońca.
{A} przysięgał{A?|a}, że ta rzecz, {kitem_a}, jest warta więcej niż reszta worka, i nikt nie oponował.
{B} chciał{B?|a} wiedzieć, gdzie to znaleziono, a {A} zapisał{A?|a} odpowiedź, żeby jej nie zapomniano.
== keep.chess
Szachownica {place_from} wyszła na końcu, pognieciona wzdłuż, bez czarnego skoczka.
Zawinięta w poszewkę szachownica {place_from}, z niemal startymi polami.
Szachownica, złożona, ze śladem po kubku z kawą; czekała {place_at}.
== keep.guitar
Struna gitarowa zwinięta w chustce {place_from} była najjaśniejszą rzeczą w worku.
Wśród puszek struna gitarowa {place_from}, błyszcząca jak drut i równie ostra.
== keep.comic
Komiks {place_from}, z do połowy zniszczoną okładką i nietkniętą twarzą bohatera.
Komiks {place_from}, kolory spłynęły, ale dowcipy nadal da się czytać.
== keep.teddy
Pluszowy miś {place_from}, jedno oko i warstwa szarego kurzu.
Pluszowy miś, brudny jak ścierka, z pękającym szwem na ramieniu, {place_from}.
== keep.seeds
Nasiona {place_from}, w papierowym zwitku z napisem „groch”, i z nie tym rokiem.
Woreczek nasion z kwiatem narysowanym długopisem, {place_from}.
== keep.cards
Karty {place_from}, miękkie jak szmatka, spięte gumką.
Talia kart w puszce {place_from}, bez jednego króla.
== keep.harmonica
Harmonijka {place_from}, zmatowiała i pełna kłaczków, którą dzieci uruchomiły w minutę.
Zawinięta w skarpetę harmonijka {place_from} i jedna czysta nuta, gdy się dmuchnęło.
== hurt.line
{B} {B?wszedł|weszła} szar{B?y|a} i milcząc{B?y|a}, z raną na {site_loc} rozdartą przez {cause_acc} {place2_at}, i obracał{B?|a} to w żart, aż zobaczył{B?|a} krew na podłodze.
{B} {B?wszedł|weszła} kulejąc, z raną na {site_loc} po trafieniu {cause_gen}, a to, co tkwiło w środku, {A} musiał{A?|a} wycinać przy stole.
{B} oberwał{B?|a} {cause_ins} w {site_acc} {place_at} i całą drogę do domu trzymał{B?|a} ranę zamkniętą pięścią.
{B} upadł{B?|a} {place2_at} i wstał{B?|a} znowu, z raną na {site_loc} rozdartą przez {cause_acc}, i nie usiadł{B?|a}, dopóki nie usiedli inni.
{B} powiedział{B?|a}, że to nic, i wtedy ugięło się pod {B?nim|nią} kolano, a rana na {site_loc} wyglądała jak po trafieniu {cause_gen}.
{B} nie idzie na następną wyprawę; zadbało o to trafienie {cause_gen} {place2_at}, w {site_acc}.
{B} {B?przyniósł|przyniosła} do domu ranę po trafieniu {cause_gen} w {site_acc}, a wszyscy {camp_at} patrzyli, jak {B} wchodzi po schodach, stopień po stopniu.
== win.after_loss
Wczoraj {prev_map_at} zabrano wszystko, a dziś {A} boi się cieszyć wygraną {map_at}, żeby i jej nie odebrano.
Po {prev_map_loc} {A} nie śmiał{A?|a} wierzyć w dobry dzień, a teraz musi udawać, że nie wierzy.
Wspomnienie {prev_map_gen} wciąż siedzi w kącie pokoju, a {A} kiwa do niego głową: nie dziś.
== down.you
{A} spojrzał{A?|a} na szew {ysite_at}, założony po {ymap_loc} w dniu {yd}, i powiedział{A?|a}, że robota trzyma się lepiej niż człowiek.
Kolejna rana obok tej po {ymap_loc} (dzień {yd}); {A} zaczyna traktować twoje ciało jak mapę.
Stara rana {ysite_at} po {ymap_loc} (dzień {yd}) źle zniosła nowy cios i {A} musiał{A?|a} ją zszyć od nowa.
== tail.calm
{B} {B?przyniósł|przyniosła} kubek czegoś ciepłego i zostawił{B?|a} go bez słowa.
Nikt nie mówił o tym przez resztę wieczoru, co było właściwym sposobem mówienia o tym.
Lampa paliła się coraz niżej, a {camp_at} powoli zasypiano.
{B} zauważył{B?|a}, nic nie powiedział{B?|a} i {B?poszedł|poszła} po dobry koc.
Dzieci usłyszały, zgadywały, zgadły źle i wysłano je do łóżek.
{B} posiedział{B?|a} chwilę obok {A?niego|niej}, nic nie mówiąc, bo nie trzeba było nic mówić.
Wiatr napierał na okiennice {camp_at} i nikt tego nie skomentował.
Czajnik wyśpiewał się do cichego szumu na piecu.
{B} {B?położył|położyła} rękę na {A?jego|jej} ramieniu i znów ją zabrał{B?|a}.
Pies przyszedł i położył się wszystkim na nogach, jak psy, gdy coś wisi w powietrzu.
== tail.good
Ktoś zaczął nucić i po chwili nucili wszyscy.
Wieczór zakończył się dodatkową kromką chleba, która była pomysłem nikogo i wszystkich.
{B} zaśmiał{B?|a} się, co się rzadko zdarza, a potem zrobił{B?|a} to jeszcze raz, żeby mieć pewność.
Przez godzinę nie mówiono o wojnie i była to dobra godzina.
Dzieciom pozwolono posiedzieć dłużej i zasnęły na podłodze, tam gdzie siedziały.
{B} powiedział{B?|a}, że to najlepszy dzień od miesiąca, i usłyszał{B?|a}, żeby nie kusić losu.
Nawet agregat zdawał się pracować przez to lepiej.
== tail.bad
{B} powiedział{B?|a}, że rano będzie lepiej, nikt w to nie uwierzył i wszyscy zasnęli.
Lampę przygaszono wcześnie i {camp_at} zrobiło się ciemno przed czasem.
{B} czuwał{B?|a} razem z {A?nim|nią} i żadne nie powiedziało ani słowa.
Ktoś płakał za zasłoną, cicho, i nikt nie poszedł zobaczyć.
Wiatr w belkach dachu, trzaskający stary piec i nic więcej.
{B} dorzucił{B?|a} do pieca resztę dobrego drewna i powiedział{B?|a}, że to na dzisiejszą noc.
Pies nie chciał jeść i nikt go nie zmuszał.
== death.line
{A} {A?rozwinął|rozwinęła} {D?zmarłemu|zmarłej} rękawy na nadgarstki i zawiązał{A?|a} mankiety, jak się robi na zimno.
Ktoś położył płaski kamień na piersi {D?zmarłego|zmarłej}, jak mówią starzy, żeby trzymał wiatr z daleka, i nikt nie pamiętał, kto.
{A} oddał{A?|a} buty {D?zmarłego|zmarłej} temu, kto potrzebował ich najbardziej, i powiedział{A?|a}, że {D} by tego chciał{D?|a}, choć nie był{A?|a} pewn{A?y|a}.
{A} przeczytał{A?|a} jedyną stronę jedynej księgi, która się otworzyła, i czytanie drżało.
Lampę {D?zmarłego|zmarłej} zostawiono na noc, przygaszoną, i nikt nie miał serca jej zgasić.
{A} kopał{A?|a} razem z dwojgiem dzieci, które uparły się pomagać, i pozwolił{A?|a} im, bo w towarzystwie kopało się łatwiej.
Piec nakarmiono krzesłem {D?zmarłego|zmarłej}, żartem, jaki {D} by zrobił{D?|a}, i nikt się nie zaśmiał, dopóki nie zaśmiał{A?|a} się {A}.
{B} stał{B?|a} nad {D?zmarłym|zmarłą} z dłonią przyciśniętą do własnych ust, potem ją zabrał{B?|a} i pożegnał{B?|a} {D?go|ją} na głos.
{A} {A?wyniósł|wyniosła} {D?go|ją} w kocu, który jeszcze trzymał ciepło {D?zmarłego|zmarłej}, i nie odłożył{A?|a} aż do grobu.
== death.title
{A} {A?zamknął|zamknęła} {D?zmarłemu|zmarłej} oczy
Obóz jest mniejszy o {D?jednego|jedną}: {D}
{D} leży w ziemi przy murze
Nikt wiele nie mówił o {D?zmarłym|zmarłej}
{A} nie {A?mógł|mogła} przestać mówić o {D?zmarłym|zmarłej}
== win.camp
W:{A} dopisał{A?|a} kolejną kreskę na ścianie {camp_at}, pod starym szablonem WLF, a kresek jest już więcej niż szablon.
W:{leader} przesłało wiadomość wzdłuż linii: dobry dzień {map_at} i podwójne racje na jeden posiłek.
S:{A} odmówił{A?|a} werset dziękczynny nad miskami, zanim komukolwiek wolno było jeść, i tym razem werset był krótki.
S:Siostry śpiewały nad brzegiem wody za wygraną, cicho, a śpiew niósł się nad przystanią.
== loss.camp
W:{A} postawił{A?|a} wszystkich {camp_at} na baczność na minutę ciszy, po czym rozpuścił{A?|a} szereg i ciężko usiadł{A?|a}.
W:{leader} przysłało gońca z jednym zdaniem, a zdanie brzmiało: jutro znowu.
S:{A} {A?uklęknął|uklękła} nad wodą i wymawiał{A?|a} imiona tego dnia, a lista była za długa na werset.
S:Słowo Proroka przyszło przez dziecko z mokrymi stopami: wyspa nie zapomina, i morze też nie.
== tail.good
W:Ktoś wciągnął starą flagę {camp_at} i tym razem nikt nie narzekał na linę.
S:Ktoś zanucił jeden z hymnów Sióstr, ten pogodny, i połowa osób {camp_at} dołączyła.
== tail.bad
W:Wartowników podwojono i noc zapadła ciężko nad {camp_ins}.
S:Jedna z Sióstr modliła się na głos w ciemności i nikt nie prosił, żeby przestała.
== tail.calm
W:Radio trzeszczało w kącie {camp_gen} głosem, który był prawie piosenką.
S:Deszcz na strzesze, miękki, równy dźwięk, a długi dom ułożył się do snu w jego rytmie.
== down.after
W:{B} powiedział{B?|a}, że medycy w bazie zszywali gorsze rzeczy i szli potem na obiad.
S:{B} {B?położył|położyła} ci wilgotną szmatkę na czole i mruczał{B?|a} jeden ze starych wersetów, i werset trochę pomógł.
== prep.event
W:{A} rozpisał{A?|a} na skrzynce z racjami kolejność następnego natarcia: kto idzie pierwszy, kto niesie, kto zostaje na murze z karabinem {leader_gen}.
S:{A} wypowiedział{A?|a} plan cicho w długim domu, jak się mówi modlitwę, a Siostry kiwały głowami we właściwych miejscach.
== keepcb.cards
Talia {kplace_from} straciła w drugim tygodniu damę kier. {A} {A?narysował|narysowała} nową ogryzkiem ołówka i od tamtej pory jest znacznie lepszą damą.
Nikomu nie wolno już grać o jedzenie talią {kmap_from}, więc {A} i {B} grają o dyżury, a naczynia są najczystsze od roku.
{A} {A?rozdał|rozdała} nocnej warcie karty {kplace_from} i przez godzinę nikt nie patrzył na drogę. Nocna warta nie po to jest. Wszystkim wyszło to na dobre.
"""
