"""Polish clan saga templates for the supplies scenes: line for line parallel to clan_saga_text_sup.py.  See clan_saga_pl.py for the rules."""
TEXT = r"""
== inj.title
{A} i rana na {site_loc}, która się nie goi
Kulawy powrót {kmap_from} trwa nadal
{A} wciąż sprawdza ranę na {site_loc}
Znowu rana na {site_loc}
{A} ma się gorzej, niż mówi
Blizna w trakcie powstawania na {site_loc}
{A}: rana na {site_loc}, tydzień później
Bandaże i {A}
== rel.title
{A} i {B} po kolacji
{A} i {B}, znów coś między nimi
{A} i {B}: czego nie mówią
{A} i {B}: kilka notatek
{A} i {B}, obok siebie
Coś w tym, jak siedzą {A} i {B}
Dwoje na końcu stołu
{B}, a {A} to zauważa
== win.hs
{hs_nom}, a {A} przysięga, że przy każdym w pokoju robiło się cicho.
{hs_nom} z linii, a {A} chce, żeby każdy z nich został narysowany na ścianie.
{hs_nom}, a {A} {A?zaczął|zaczęła} wyciągać ręce, jakby chciał{A?|a} poczuć odrzut z drugiej ręki.
{hs_nom}, i nikt nie kwestionował tego, jak to opowiedziano.
{hs_nom}, a {A} mówi, że starzy nazwaliby to szczęściem i zaraz by się przeżegnali.
== lack.title
{A} został{A?|a} bez niczego
Spiżarnia wyschła
Znowu za mało
Za mało na stole
{A} oddał{A?|a} resztkę
Czego dzień nie przyniósł
== lack.food
Puszki skończyły się, zanim {A} dostał{A?|a} porcję, a garnek wyskrobano dwa razy dla tego, co zostało.
{A} żuł{A?|a} pasek suchej skórki do końca i nazwał{A?|a} to kolacją. W worku było o {lack_n_acc} mniej, niż obóz zjadał.
{A} położył{A?|a} się spać głodn{A?y|a} i cały pokój to słyszał. Zabrakło {lack_n_gen} jedzenia.
Nikt nie miał odwagi liczyć pustych talerzy. Jednym z nich był {A?jego|jej} talerz.
{A} podzielił{A?|a} jedną puszkę fasoli na czworo i {A?wziął|wzięła} najmniejszą część, a spiżarnia starczała na {lack_days} jedzenia.
Kuchnię wymieciono do czysta. {A} oblizał{A?|a} łyżkę i odłożył{A?|a} ją bez słowa.
{A} {A?przesunął|przesunęła} miskę w stronę {B?niego|niej} i powiedział{A?|a}, że już jadł{A?|a}, w co nikt nie uwierzył.
== lack.water
Beczki opróżniały się szybko i o zmierzchu {A} dzielił{A?|a} kubek z {B?nim|nią}.
{A} dwa razy gotował{A?|a} ten sam garnek wody. Brakowało obozowi {lack_n_gen} wody i wszyscy o tym wiedzieli.
Usta {A?jego|jej} były wieczorem spękane, a racja wody nie starczyła na drugi kubek.
Wodę liczono łykami. {A} zmoczył{A?|a} szmatę i przyłożył{A?|a} ją do szyi zamiast pić.
Filtr kapał całą noc, a rano {A} stał{A?|a} w kolejce {A?pierwszy|pierwsza} z pustą butelką.
Mając w beczkach wodę na {lack_days}, {A} przestał{A?|a} się myć i {A?zaczął|zaczęła} oszczędzać.
== lack.med
Ostatni bandaż poszedł na kogoś innego, a {A} leżał{A?|a} spokojnie i o niego nie prosił{A?|a}.
{A} drżał{A?|a} pod dwoma płaszczami. Na półce z lekarstwami brakowało {lack_n_gen} tego, czego potrzebują chorzy, i obóz wie, co to znaczy.
Na gorączkę były tylko zimne okłady. {A} powiedział{A?|a}, że do rana głowa się przejaśni, i się nie przejaśniła.
{A} dwa razy przeliczył{A?|a} tabletki w puszce. Nie starczało ich na nocną dawkę dla wszystkich, którzy jej potrzebowali.
Antybiotyki skończyły się, zanim doszło do {A?niego|niej}, i {B} czuwał{B?|a} przy {A?nim|niej} zamiast tego.
Mając na półce lekarstwa na {lack_days}, {A} patrzył{A?|a} na puszkę tak, jak inni patrzą na drzwi.
== lack.tail
Niedobór jest zapisany kredą na tablicy przy drzwiach i nikt go nie ściera.
Następna wyprawa musi to przynieść z powrotem, inaczej znów się to zdarzy.
Widać to na każdej twarzy, nawet gdy nikt tego nie mówi.
{B} powiedział{B?|a}, że to się nie utrzyma, i wciąż patrzył{B?|a} na garnek.
Ktoś zapisał to w księdze, jakby zapisanie miało napełnić półkę.
== haul.finds
Szczegóły opowiedziano nad otwartym workiem. {finds_text}
Każdy chciał usłyszeć historię każdej rzeczy. {finds_text}
Lista nie mówi, jak to znaleziono. {finds_text}
Część z tego przyszła z własną historią. {finds_text}
{A} odczytał{A?|a} znaleziska jak wiersz. {finds_text}
Nic nie wróciło do domu bez miejsca, które się pamięta. {finds_text}
Rachunek chowa drobiazgi. {finds_text}
{B} zapisał{B?|a} każdą rzecz razem z miejscem, gdzie ją znaleziono. {finds_text}
== keepfind.title
Znalezisko: {kfind} {kmap_from}
Co {A} zrobił{A?|a} ze znaleziskiem {kmap_from}
Znalezisko z dnia {kd}
Drobiazg {kmap_from}
== keepfind.line
Znalezisko {kmap_from} (dzień {kd}), czyli {kfind}, od tamtej pory nie opuszcza kieszeni {A}. Dzieci o to pytają, a {A} za każdym razem opowiada inaczej.
{A} przetarł{A?|a} mokrym kciukiem znalezisko {kmap_from} ({kfind}) i postawił{A?|a} je tam, gdzie pada światło lampy. Nie należy do nikogo i do wszystkich.
Ktoś zapytał, skąd jest {kfind}. {A} powiedział{A?|a}, że {kmap_from}, z dnia {kd}, i opowiedział{A?|a} całą historię, razem z tym, co się nie wydarzyło.
Znalezisko z dnia {kd}, czyli {kfind}, stoi na półce przy drzwiach. {B} dotyka go przy każdym wyjściu, na szczęście.
Nikt nie potrzebował znaleziska {kmap_from}, czyli {kfind}, i właśnie dlatego {A} nie chciał{A?|a} go wymienić.
{A} oddał{A?|a} dzienną porcję zupy, żeby obejrzeć znalezisko ({kfind}), i nazwał{A?|a} to najlepszą ceną, jaką obóz kiedykolwiek zapłacił.
== dep.title
{A} przestał{A?|a} odzywać się przy stole
{A} i długie milczenie
Nikt nie mógł dotrzeć do {A}
{A} i puste godziny
== dep.line
{A} przestał{A?|a} przychodzić do ogniska. Jedzenie leży na talerzu, kiedy {B} je przynosi, i nadal leży, gdy {B} wraca.
Od kilku dni {A} nie powiedział{A?|a} niczego, co nie byłoby odpowiedzią. {B} siedzi blisko i nie pyta, a to wszystko, co można zrobić.
{A} patrzy na ścianę, na której kredą zapisano rachunek dnia. Liczby od dawna nie rosną, a {A} przestał{A?|a} udawać, że urosną.
Ktoś zastał {A} w ciemności, przy zgaszonej lampie. Nikt nic nie powiedział; {B} po prostu usiadł{B?|a} po drugiej stronie drzwi.
{A} złożył{A?|a} koc, rozłożył{A?|a} go i złożył{A?|a} jeszcze raz. To jedyna rzecz w obozie, którą {A} jeszcze potrafi skończyć.
Obóz jest chudy, a półki jeszcze chudsze, i {A} odszedł{A?|a} gdzieś, gdzie nikt za {A?nim|nią} nie może pójść. Dobry wypad mógłby {A?go|ją} przywrócić.
== dep.up
{A} zjadł{A?|a} dziś całą miskę i poprosił{A?|a} o sól. {B} odwrócił{B?|a} wzrok, żeby nikt nie zobaczył uśmiechu.
Wypad pomógł. {A} przyszedł{A?|a} do ogniska, {A?wyciągnął|wyciągnęła} do niego obie dłonie i pierwszy raz od dni powiedział{A?|a} całe zdanie.
{A} dochodzi do siebie: trochę mowy, trochę zupy. {B} pilnuje, ale tak, żeby nie wyglądało to na pilnowanie.
"""
