"""A-Life text pools, part C: threats, neighbours and trade, rumours, camp scenes by role, weather openers.  Row format: see clan_alife_text_a.py."""

POOLS = {}

# ---- threats: A on watch (B beside), enemy / enemies / inf come from the faction, dest = where it was seen
POOLS["thr_enemy"] = [
    ("*", "*", "{A} sees smoke from a {enemy} camp near {dest}, thin and careful, the smoke of people who do not want to be seen. {B} climbs up to look too.",
     "{A} widzi dym z obozu {enemy_gen} {dest_at}, cienki i ostrożny, dym ludzi, którzy nie chcą być widziani. {B} wspina się, żeby też spojrzeć."),
    ("*", "*", "A {enemy} patrol was counted at {dest} by the watch. {A} says six. {B} says nine. The truth is probably seven, and bad.",
     "Warta policzyła patrol {enemy_gen} {dest_at}. {A} mówi, że sześciu, {B}, że dziewięciu. Prawda to pewnie siedmiu i to źle."),
    ("W", "*", "Radio chatter near {dest}: Scar voices, close. {A} turns the volume down and the watch up.",
     "Trzaski w radiu w okolicy {dest_gen}: głosy Blizn, blisko. {A} ścisza radio i wzmacnia wartę."),
    ("S", "*", "{A} finds Wolf boot prints on the shore near {dest}, and a cut line where a boat should be. {B} says the island is being counted.",
     "{A} znajduje ślady wilczych butów na brzegu {dest_gen} i przeciętą cumę tam, gdzie powinna być łódź. {B} mówi, że wyspę ktoś liczy."),
]
POOLS["thr_inf"] = [
    ("*", "*", "{A} reports a bunch of {infs} moving through {dest}, slowly, the way they do in the cold. {B} adds a second watch to the east side.",
     "{A} melduje grupę {infs_gen} przesuwającą się {dest_at}, powoli, tak jak robią to w zimnie. {B} dokłada drugą wartę od wschodu."),
    ("*", "*", "A {inf} was heard in the night near {dest}. The watch lay flat and quiet. It went away; nobody slept anyway.",
     "W nocy w okolicy {dest_gen} słychać było {inf_gen}. Warta leżała płasko i cicho. Odszedł; nikt i tak nie spał."),
    ("*", "b", "More {infs} than usual around {dest}. {A} says it is the weather. {B} says {A} has been wrong about the weather before.",
     "Więcej {infs_gen} niż zwykle {dest_at}. {A} mówi, że to pogoda. {B} mówi, że {A} już się mylił{A?|a} co do pogody."),
]
POOLS["thr_smoke"] = [
    ("*", "*", "A pillar of smoke stands up over {dest}. {A} watches it for an hour and cannot say whose it is. {B} says that is the worst answer there is.",
     "W okolicy {dest_gen} stoi słup dymu. {A} patrzy na niego godzinę i nie umie powiedzieć, czyj to. {B} mówi, że to najgorsza możliwa odpowiedź."),
    ("*", "n", "Smoke on the horizon, thin and gray. {A} and {B} take turns watching it until the wind changes and the sky clears.",
     "Dym na horyzoncie, cienki i szary. {A} i {B} patrzą na niego na zmianę, aż zmieni się wiatr i niebo się przejaśni."),
]
POOLS["thr_up"] = [
    ("*", "*", "The signs near {dest} are not going away. {A} doubles the watch and tells everyone to sleep in their boots.",
     "Znaki w okolicy {dest_gen} nie znikają. {A} podwaja wartę i każe wszystkim spać w butach."),
    ("*", "b", "{A} says it is closer today. {B} does not ask what, because everybody knows what.",
     "{A} mówi, że dziś jest bliżej. {B} nie pyta czego, bo wszyscy wiedzą czego."),
    ("W", "*", "{A} sends a runner to the stadium to report what the watch has seen near {dest}. The answer will take a day, and the danger perhaps less.",
     "{A} wysyła gońca na stadion z raportem o tym, co warta widziała w okolicy {dest_gen}. Odpowiedź zajmie dzień, a zagrożenie może mniej."),
]
POOLS["thr_down"] = [
    ("*", "*", "Whatever was near {dest} moved on. {A} lets the extra watch stand down, though {A_he} keeps listening.",
     "Cokolwiek było w okolicy {dest_gen}, poszło dalej. {A} zwalnia dodatkową wartę, choć sam{A?|a} wciąż nasłuchuje."),
    ("*", "g", "The alarm near {dest} came to nothing. {B} calls it a mistake and {A} calls it a good drill, and both are right.",
     "Alarm w okolicy {dest_gen} okazał się niczym. {B} nazywa go pomyłką, a {A} dobrym ćwiczeniem, i oboje mają rację."),
    ("*", "n", "No more signs near {dest}. The watch goes back to its usual shifts. {A} says it was close; {B} says it was not.",
     "Znaków w okolicy {dest_gen} więcej nie ma. Warta wraca do zwykłych zmian. {A} mówi, że było blisko, {B}, że nie."),
]
POOLS["thr_after"] = [
    ("*", "*", "After the attack, {A} walks the fence line in the dark, checking every post. {B} follows with a lantern and no questions.",
     "Po ataku {A} obchodzi w ciemności linię ogrodzenia, sprawdzając każdy słup. {B} idzie za {A?nim|nią} z latarnią i bez pytań."),
    ("*", "b", "The yard still smells of smoke. {A} and {B} drag the broken things into a pile and do not talk about the people.",
     "Na podwórzu wciąż czuć dym. {A} i {B} zwlekają połamane rzeczy na stos i nie rozmawiają o ludziach."),
    ("W", "*", "The watch is doubled after the attack. {A} takes the first shift and hands {B} the second, and neither of them tries for sleep in between.",
     "Po ataku warta zostaje podwojona. {A} bierze pierwszą zmianę, a {B} drugą, i żadne z nich nawet nie próbuje spać pomiędzy."),
    ("S", "*", "After the raid the long house is quiet for a long time. Then {A} begins the reading, and {B} joins in, and one by one the rest follow.",
     "Po napaści długi dom przez długi czas milczy. Potem {A} zaczyna czytanie, {B} dołącza, a za nimi jedno po drugim pozostali."),
    ("*", "g", "The clan held the line. {A} and {B} are patching the fence, laughing a bit too loud, the way people do when they are alive.",
     "Klan utrzymał linię. {A} i {B} łatają ogrodzenie, śmiejąc się trochę za głośno, jak ludzie, którzy żyją."),
]

# ---- trade with the neighbours (grp, due = clan day of the meeting)
POOLS["tr_rumor"] = [
    ("*", "*", "Word from the road: {grp} will be at {dest} on day {due}, carrying goods. {A} starts putting together something to trade.",
     "Wieść z drogi: {grp_nom} będą {dest_at} w dniu {due} z towarem. {A} zaczyna zbierać coś na wymianę."),
    ("*", "n", "{A} heard that {grp} are coming back through {dest} around day {due}. {B} says it is only a rumour; {A} says rumours are how business starts.",
     "{A} usłyszał{A?|a}, że {grp_nom} zjawią się {dest_at} około dnia {due}. {B} mówi, że to plotka; {A} mówi, że plotka to początek interesu."),
]
POOLS["tr_meet"] = [
    ("*", "*", "{A} and {B} meet {grp} at {dest}, with the goods spread out on a blanket. Both sides count everything twice and smile with their teeth.",
     "{A} i {B} spotykają {grp_acc} {dest_at}, towar rozłożony na kocu. Obie strony liczą wszystko dwa razy i uśmiechają się zębami."),
    ("W", "*", "At {dest}, {A} haggles with {grp} over {goal} for a good hour. {B} stands behind with a rifle, to remind everyone the price is not only about money.",
     "{dest_at} {A} targuje się z {grp_ins} o {goal_acc} przez dobrą godzinę. {B} stoi z tyłu z karabinem, żeby przypomnieć, że cena to nie tylko pieniądze."),
    ("S", "*", "At {dest}, {A} leaves goods on the stone and steps back, as is the custom. {grp} take what they want, and leave {goal} in exchange.",
     "{dest_at} {A} kładzie towar na kamieniu i cofa się, jak nakazuje zwyczaj. {grp_nom} biorą, co chcą, i zostawiają w zamian {goal_acc}."),
]
POOLS["tr_good"] = [
    ("*", "g", "The trade with {grp} went well: {goal}, and a promise of more. {A} is already planning the next one.",
     "Wymiana z {grp_ins} poszła dobrze: {goal_nom}, i obietnica więcej. {A} już planuje następną."),
    ("*", "*", "{A} came back from the trade with {grp} having gotten {goal}, and with a story about a bargain. {B} says the bargain is not as good as {A} thinks.",
     "{A} wrócił{A?|a} z wymiany z {grp_ins} {goal_with} i z opowieścią o okazji. {B} mówi, że okazja nie jest taka dobra, jak sądzi {A}."),
    ("*", "n", "A fair trade with {grp}: nobody cheated, nobody was cheated. {A} calls it a miracle.",
     "Uczciwa wymiana z {grp_ins}: nikt nie oszukał, nikt nie został oszukany. {A} nazywa to cudem."),
]
POOLS["tr_bad"] = [
    ("*", "b", "{grp} never came to {dest}. {A} waited four hours, then packed the goods back up and said what {A_he} thought of traders.",
     "{grp_nom} nie przybyli {dest_to}. {A} czekał{A?|a} cztery godziny, potem zapakował{A?|a} towar z powrotem i powiedział{A?|a}, co myśli o handlarzach."),
    ("*", "*", "The deal with {grp} fell apart over a price. {A} says {A_he} will not be taken for a fool; {B} says {A} was.",
     "Umowa z {grp_ins} rozpadła się o cenę. {A} mówi, że nie da się wziąć za głupca; {B} mówi, że już się dał{A?|a}."),
]

# ---- rumours and news (A hears / tells)
POOLS["rumor"] = [
    ("W", "*", "{A} heard on the radio that the Scars are moving boats at night. {B} says that is what the radio always says.",
     "{A} usłyszał{A?|a} w radiu, że Blizny nocą przemieszczają łodzie. {B} mówi, że radio zawsze to mówi."),
    ("S", "*", "{A} says the Wolves have been seen on the mainland shore, more of them than before. {B} says that is what they want us to think.",
     "{A} mówi, że Wilków widziano na brzegu lądu, więcej niż wcześniej. {B} mówi, że właśnie tak chcą, żebyśmy myśleli."),
    ("W", "*", "A rumour is going round the barracks: the stadium has a new shipment of medicine coming. {A} believes it. {B} hopes it.",
     "Po koszarach krąży plotka: na stadion ma przyjść nowa dostawa leków. {A} w to wierzy. {B} ma nadzieję."),
    ("S", "*", "The weavers say the Prophet has a new vision of the mainland. {A} says it is a warning; {B} says it is a plan.",
     "Tkacze mówią, że Prorok miał nową wizję lądu. {A} mówi, że to ostrzeżenie, {B}, że to plan."),
    ("*", "*", "{A} swears {A_he} saw a deer in the ruins, a live one. Nobody believes {A_him}, and everybody goes to look.",
     "{A} przysięga, że widział{A?|a} w ruinach jelenia, żywego. Nikt {A?mu|jej} nie wierzy, ale wszyscy idą go zobaczyć."),
    ("*", "n", "The talk by the fire is of the other clans: who has the better stores, who the better walls. {A} says it does not matter. {B} says it matters a great deal.",
     "Przy ogniu mówi się o innych klanach: kto ma lepsze zapasy, kto lepsze mury. {A} mówi, że to bez znaczenia. {B} mówi, że znaczy bardzo wiele."),
    ("*", "*", "A trader passing through says the coast road is open again. {A} writes it down, then crosses it out, then writes it down again.",
     "Przejezdny handlarz mówi, że droga nadbrzeżna jest znów przejezdna. {A} zapisuje to, potem skreśla, potem znowu zapisuje."),
    ("*", "b", "{A} tells a story about a settlement that starved to the last man. {B} asks {A} to stop. {A} does, but the story stays.",
     "{A} opowiada historię o osadzie, która wymarła z głodu do ostatniego człowieka. {B} prosi, żeby przestał{B?|a}. {A} przestaje, ale historia zostaje."),
]

# ---- camp scenes (A, B, C = healthy members who are in camp)
POOLS["amb_any"] = [
    ("*", "*", "{A} and {B} hang the washing between two posts. The first gust takes half of it, and they spend an hour chasing socks.",
     "{A} i {B} wieszają pranie między dwoma słupkami. Pierwszy podmuch zabiera połowę i godzinę gonią skarpetki."),
    ("*", "g", "{A} teaches the camp a card game; {B} loses three times and swears {B_he} will win it back. The pot is a boiled egg.",
     "{A} uczy obóz gry w karty; {B} przegrywa trzy razy i przysięga, że się odegra. Stawką jest jajko na twardo."),
    ("*", "*", "{A} finds a mouse in the flour barrel and makes a ceremony of putting it outside. {B} would have used a boot.",
     "{A} znajduje mysz w beczce z mąką i urządza ceremonię wynoszenia jej na zewnątrz. {B} użył{B?|a}by buta."),
    ("*", "n", "{A} mends a coat by the fire while {B} reads aloud from the only book the clan owns. It is the third time through; nobody minds.",
     "{A} łata płaszcz przy ogniu, a {B} czyta na głos jedyną książkę, jaką ma klan. To trzeci raz; nikt nie ma nic przeciwko."),
    ("*", "b", "{A} cannot sleep and walks the yard. {B} cannot sleep either, and they pass each other twice without a word.",
     "{A} nie może spać i chodzi po podwórzu. {B} też nie może spać i mijają się dwa razy bez słowa."),
    ("*", "*", "{A}, {B} and {C} play a long, quiet game with stones and chalk in the dust. Nobody explains the rules; nobody wins.",
     "{A}, {B} i {C} grają długą, cichą grę kamieniami i kredą w pyle. Nikt nie tłumaczy zasad; nikt nie wygrywa."),
    ("*", "*", "{A} is trying to teach a stray dog to sit. The dog is trying to teach {A} to share.",
     "{A} próbuje nauczyć bezpańskiego psa siadać. Pies próbuje nauczyć {A?go|ją} dzielić się."),
    ("*", "g", "Somebody found a harmonica. {A} plays it badly, and {B} plays it worse, and the camp sings along with both.",
     "Ktoś znalazł harmonijkę. {A} gra na niej kiepsko, {B} gorzej, a obóz śpiewa do obojga."),
    ("*", "*", "{A} and {B} bury a box of old photographs under the north wall, as an act of hope, they say. {C} says it is an act of vanity.",
     "{A} i {B} zakopują pod północnym murem pudełko starych fotografii, jako akt nadziei, jak mówią. {C} mówi, że to akt próżności."),
    ("*", "n", "{A} repairs the fence while {B} keeps watch. They trade turns at noon without looking at each other, the way old partners do.",
     "{A} naprawia ogrodzenie, a {B} pilnuje. W południe zamieniają się bez patrzenia na siebie, jak starzy partnerzy."),
    ("*", "b", "{A} sits at the edge of the firelight with {A_his} back to the others. {B} sits down next to {A_him} and says nothing for an hour.",
     "{A} siedzi na skraju światła ogniska plecami do reszty. {B} siada obok i przez godzinę nic nie mówi."),
    ("*", "*", "{A} and {B} count the candles and come to different answers. They count again. The candles are fewer.",
     "{A} i {B} liczą świece i dochodzą do różnych wyników. Liczą jeszcze raz. Świec jest mniej."),
    ("W", "*", "{A} and {B} set up a ball game on the old field, with a rag-ball and rules from a sport that no longer exists. The stadium echoes with it.",
     "{A} i {B} organizują grę w piłkę na starym boisku, szmacianką i według zasad sportu, którego już nie ma. Stadion odbija echo."),
    ("W", "*", "The generator coughs twice and dies. {A} swears at it in four languages; {B} kicks it in the one that works.",
     "Agregat kaszle dwa razy i gaśnie. {A} przeklina go w czterech językach, a {B} kopie w tym, który działa."),
    ("W", "*", "{A} paints a name on the wall of the barracks: not a person, a place. {B} asks where it is. {A} says it is where we are going.",
     "{A} maluje na ścianie koszar nazwę: nie osoby, miejsca. {B} pyta, gdzie to jest. {A} mówi, że tam, dokąd zmierzamy."),
    ("W", "*", "Roll call at the stadium gate. {A} shouts the names; {B} shouts back the ones that are present, and then, quieter, the ones that are not.",
     "Apel przy bramie stadionu. {A} wykrzykuje nazwiska, a {B} odkrzykuje obecnych, a potem, ciszej, tych, których brak."),
    ("S", "*", "{A} and {B} mend a net by the shore while the sea works at the stones behind them. It is a long conversation made of very few words.",
     "{A} i {B} naprawiają sieć na brzegu, podczas gdy morze pracuje przy kamieniach za nimi. To długa rozmowa złożona z bardzo niewielu słów."),
    ("S", "*", "The evening reading is {A}'s turn. {A} reads slowly, and {B} listens with {B_his} eyes closed, and the long house is for a moment very still.",
     "Wieczorne czytanie prowadzi dziś {A}; czyta powoli, a {B} słucha z zamkniętymi oczami, i długi dom na chwilę całkiem cichnie."),
    ("S", "*", "{A} and {B} gather driftwood after the tide. {B} finds a doll and puts it, face down, on a high shelf, for the children not to see.",
     "{A} i {B} zbierają wyrzucone przez przypływ drewno. {B} znajduje lalkę i kładzie ją twarzą w dół na wysokiej półce, żeby dzieci nie widziały."),
    ("S", "*", "{A} stands on the shore at dawn, as {A_he} does every morning, and sings the first hymn to the water. {B} joins for the second verse.",
     "{A} staje o świcie na brzegu, jak co rano, i śpiewa pierwszy hymn do wody. {B} dołącza przy drugiej zwrotce."),
]
POOLS["amb_scavenger"] = [
    ("*", "*", "{A}, the {A_role}, empties the bag on the floor and sorts it into piles: useful, maybe, and no. The 'no' pile is the biggest.",
     "{A}, {A_role}, wysypuje torbę na podłogę i sortuje na stosy: przydatne, może i nie. Stos „nie” jest największy."),
    ("*", "n", "{A} comes back from a short run with a bag of acorns, two bent forks, and the quiet pride of someone who found something.",
     "{A} wraca z krótkiej wyprawy z workiem żołędzi, dwoma wygiętymi widelcami i cichą dumą kogoś, kto coś znalazł."),
    ("*", "g", "{A} shows {B} a scrap of map that leads, supposedly, to a pantry nobody has looted. {B} asks if {A} has been drinking. {A} says only a little.",
     "{A} pokazuje {B?mu|jej} skrawek mapy, który ma prowadzić do spiżarni, której nikt nie splądrował. {B} pyta, czy {A} pił{A?|a}. {A} mówi, że tylko trochę."),
]
POOLS["amb_medic"] = [
    ("*", "*", "{A}, the {A_role}, boils the bandages again and hangs them to dry. The camp has learned not to walk under them.",
     "{A}, {A_role}, znów gotuje bandaże i wiesza je do wyschnięcia. Obóz nauczył się nie chodzić pod nimi."),
    ("*", "n", "{A} goes through the medicine shelf with a pencil and a face that says the shelf is shorter than last week.",
     "{A} przegląda półkę z lekami z ołówkiem i miną, która mówi, że półka jest krótsza niż w zeszłym tygodniu."),
    ("*", "g", "{A} gives the whole camp a lecture on boiling water. {B} says {B_he} has heard it. {A} says {B_he} has not listened.",
     "{A} wygłasza całemu obozowi wykład o gotowaniu wody. {B} mówi, że już to słyszał{B?|a}. {A} mówi, że nie słuchał{B?|a}."),
]
POOLS["amb_cook"] = [
    ("*", "*", "{A}, the {A_role}, tastes the soup, makes a face, and adds the one ingredient nobody can identify. It improves.",
     "{A}, {A_role}, próbuje zupy, krzywi się i dodaje jedyny składnik, którego nikt nie umie nazwać. Jest lepsza."),
    ("*", "b", "{A} stirs the pot for an hour, and every time someone asks what is for dinner, answers 'food' in a tone that closes the conversation.",
     "{A} miesza w garnku od godziny i za każdym razem, gdy ktoś pyta, co na obiad, odpowiada „jedzenie” tonem, który zamyka rozmowę."),
    ("*", "g", "{A} makes bread, real bread, with the last of the good flour. The smell crosses the yard and stops all work.",
     "{A} piecze chleb, prawdziwy chleb, z ostatniej dobrej mąki. Zapach przechodzi przez podwórze i zatrzymuje wszelką pracę."),
]
POOLS["amb_guard"] = [
    ("*", "*", "{A}, the {A_role}, has a theory about which of the three dogs barks first and keeps a tally on the post. The dogs do not care.",
     "{A}, {A_role}, ma teorię, który z trzech psów szczeka pierwszy, i prowadzi rachunek na słupie. Psy się tym nie przejmują."),
    ("*", "n", "{A} takes the night watch, and {B} brings tea at three in the morning, and neither of them mentions it later.",
     "{A} bierze nocną wartę, a {B} przynosi herbatę o trzeciej w nocy i żadne z nich potem o tym nie wspomina."),
    ("*", "b", "{A} does the rounds twice an hour now. {B} says it is for the nerves; {A} says it is for the people.",
     "{A} obchodzi teren dwa razy na godzinę. {B} mówi, że to dla nerwów; {A} mówi, że dla ludzi."),
]
POOLS["amb_mechanic"] = [
    ("*", "*", "{A}, the {A_role}, takes something apart that was working, to see why. It is a small tragedy; then it works better.",
     "{A}, {A_role}, rozbiera coś, co działało, żeby sprawdzić dlaczego. To mała tragedia; potem działa lepiej."),
    ("*", "n", "{A} has a vise, a file, and a plan. {B} has a bad feeling about the plan. The vise decides.",
     "{A} ma imadło, pilnik i plan. {B} ma złe przeczucia co do planu. Imadło rozstrzyga."),
    ("*", "g", "{A} made a lock for the storeroom out of a bicycle chain and a spoon. It is the best lock the clan has ever had.",
     "{A} zrobił{A?|a} zamek do magazynu z łańcucha rowerowego i łyżki. To najlepszy zamek, jaki klan kiedykolwiek miał."),
]
POOLS["amb_scout"] = [
    ("*", "*", "{A}, the {A_role}, is back from the ridge with a drawing of the valley and the news that nothing has changed, which is itself news.",
     "{A}, {A_role}, wraca z grzbietu z rysunkiem doliny i wiadomością, że nic się nie zmieniło, co samo w sobie jest wiadomością."),
    ("*", "n", "{A} checks the trip lines on the south road, resets two, and finds a dead crow tied to the third. {B} says it is a joke. {A} asks who it is for.",
     "{A} sprawdza linki na południowej drodze, ustawia dwie od nowa i znajduje martwą wronę przywiązaną do trzeciej. {B} mówi, że to żart. {A} pyta, dla kogo."),
]
POOLS["amb_gardener"] = [
    ("*", "*", "{A}, the {A_role}, talks to the beans. {B} says they grow better for it. {A} says it is for the company.",
     "{A}, {A_role}, rozmawia z fasolą. {B} mówi, że dzięki temu rośnie lepiej. {A} mówi, że to dla towarzystwa."),
    ("*", "g", "The first green shoots in the garden: {A} stands over them for an hour, and nobody has the heart to say it is only grass.",
     "Pierwsze zielone pędy w ogrodzie: {A} stoi nad nimi godzinę i nikt nie ma serca powiedzieć, że to tylko trawa."),
    ("*", "b", "Frost took half of the garden. {A} sits on the edge of the bed, picking at the earth, saying the names of what was planted.",
     "Mróz zabrał połowę ogrodu. {A} siedzi na skraju grządki, dłubiąc w ziemi, i wymienia nazwy tego, co posadzono."),
]
POOLS["amb_kid"] = [
    ("*", "*", "{A}, the {A_role}, has built a fort from crates and a tarp and announced a toll. {B} pays it in buttons.",
     "{A}, {A_role}, zbudował{A?|a} fort ze skrzyń i plandeki i ogłosił{A?|a} myto. {B} płaci guzikami."),
    ("*", "g", "{A} asks {B} how the world was before. {B} says, 'louder,' and for once nobody laughs; they listen.",
     "{A} zagaduje: jaki był świat dawniej? {B} mówi: „głośniejszy”, i tym razem nikt się nie śmieje; słuchają."),
    ("*", "n", "{A} is caught drawing on the storeroom wall. It is a picture of a dog, a house, and the whole clan, with the number of people correct.",
     "{A} zostaje przyłapan{A?y|a} na rysowaniu na ścianie magazynu. To obrazek psa, domu i całego klanu, z poprawną liczbą ludzi."),
    ("*", "b", "{A} asks, very quietly, if the grown-ups are afraid. {B} says no. {A} says that is what they say when they are.",
     "{A} pyta bardzo cicho, czy dorośli się boją. {B} mówi, że nie. {A} mówi, że tak właśnie mówią, kiedy się boją."),
]
POOLS["amb_elder"] = [
    ("*", "*", "{A}, the {A_role}, tells the story of the old days again, and this time the ending is different. {B} lets {A_him} have it.",
     "{A}, {A_role}, znów opowiada historię dawnych dni i tym razem zakończenie jest inne. {B} pozwala {A?mu|jej} na to."),
    ("*", "n", "{A} sits in the best chair, by the stove, and gives out advice nobody wants. Half of it is good, which is the worst part.",
     "{A} siedzi w najlepszym fotelu przy piecu i rozdaje rady, których nikt nie chce. Połowa jest dobra, i to najgorsze."),
    ("*", "g", "{A} remembers a recipe from before, and for an evening the whole camp argues about whether it can be made with what they have.",
     "{A} przypomina sobie przepis sprzed lat i przez wieczór cały obóz spiera się, czy da się go zrobić z tego, co mają."),
]
POOLS["amb_radio"] = [
    ("W", "*", "{A}, the {A_role}, sits over the set for an hour and picks up only static and, once, three notes of a song. {A} swears it was a song.",
     "{A}, {A_role}, siedzi nad aparatem godzinę i łapie tylko szum i raz trzy nuty piosenki. {A} przysięga, że to była piosenka."),
    ("W", "n", "{A} reads the evening bulletin from the stadium: three items, a weather report, and a joke that is the same as last week's. The room laughs anyway.",
     "{A} czyta wieczorny komunikat ze stadionu: trzy punkty, prognozę pogody i ten sam żart co w zeszłym tygodniu. Sala i tak się śmieje."),
    ("S", "n", "{A}, who weaves, hums the pattern aloud so it will not be lost. {B} learns the hum, and the weaving goes on in two voices.",
     "{A}, {A?który|która} tka, nuci wzór na głos, żeby go nie zgubić. {B} uczy się nuty i tkanie toczy się dwoma głosami."),
]

# ---- weather openers (one sentence, no people)
POOLS["wx_rain"] = [
    ("*", "*", "Rain again, steady and cold, the kind that finds the gaps in every coat.", "Znów deszcz, równy i zimny, taki, który znajduje dziury w każdym płaszczu."),
    ("W", "*", "Rain drums on the stadium roof, and every bucket in the barracks is working.", "Deszcz bębni po dachu stadionu i każde wiadro w koszarach jest w robocie."),
    ("S", "*", "Rain walks across the water in gray sheets, and the island disappears behind it.", "Deszcz idzie po wodzie szarymi płachtami, a wyspa znika za nim."),
]
POOLS["wx_fog"] = [
    ("*", "*", "Fog this morning, thick enough that the gate watch cannot see the yard.", "Dziś rano mgła, tak gęsta, że warta przy bramie nie widzi podwórza."),
    ("S", "*", "Sea fog has swallowed the island, and the bell on the shore post rings every quarter hour.", "Morska mgła połknęła wyspę, a dzwon na słupie przy brzegu bije co kwadrans."),
    ("W", "*", "Fog over the stadium; the floodlights make halos and no light.", "Mgła nad stadionem; reflektory dają halo, a nie światło."),
]
POOLS["wx_cold"] = [
    ("*", "*", "A hard cold has come in overnight, and the water in the barrels is skinned with ice.", "W nocy przyszedł ostry mróz i woda w beczkach pokryła się lodem."),
    ("*", "b", "The cold is the kind that makes hunger worse. People wrap themselves in everything they own.", "To taki mróz, który pogarsza głód. Ludzie owijają się wszystkim, co mają."),
    ("W", "*", "The cold has the stadium shivering, and the generator is rationed to the sick bay and the radio.", "Mróz trzęsie stadionem, a agregat jest racjonowany dla izby chorych i radia."),
    ("S", "*", "Cold wind from the strait; the long house burns twice the driftwood and nobody complains.", "Zimny wiatr z cieśniny; długi dom spala dwa razy więcej drewna i nikt nie narzeka."),
]
POOLS["wx_clear"] = [
    ("*", "g", "A clear day, a hard blue sky, the first in a week. Everything looks better in it.", "Pogodny dzień, twarde błękitne niebo, pierwsze od tygodnia. W nim wszystko wygląda lepiej."),
    ("*", "*", "The sky is clear and the air smells of cold stone. Sounds go a long way.", "Niebo jest czyste, a powietrze pachnie zimnym kamieniem. Dźwięki niosą się daleko."),
    ("*", "n", "The sun came out for an hour, and half the camp stood in it with their eyes closed.", "Wyszło słońce na godzinę i połowa obozu stała w nim z zamkniętymi oczami."),
    ("S", "*", "The strait is flat and bright, and the far shore looks close enough to touch, and just as dangerous.", "Cieśnina jest gładka i jasna, a drugi brzeg wygląda na tyle blisko, by go dotknąć, i równie niebezpiecznie."),
]
POOLS["wx_smoke"] = [
    ("*", "*", "Smoke from somewhere hangs over the camp, thin and sour, and nobody can say where it comes from.", "Dym skądś zawisł nad obozem, cienki i kwaśny, i nikt nie wie skąd."),
    ("*", "b", "The air is brown with smoke today, and the clan breathes it like a debt.", "Powietrze jest dziś brunatne od dymu, a klan oddycha nim jak długiem."),
    ("W", "*", "Someone is burning something across the river. The watch goes up to look and comes back down quiet.", "Ktoś pali coś za rzeką. Warta idzie na górę zobaczyć i wraca cicha."),
]
POOLS["wx_wind"] = [
    ("*", "*", "A strong wind has been pushing at the walls since noon, and every loose board is talking.", "Silny wiatr napiera na ściany od południa, a każda luźna deska coś mówi."),
    ("*", "*", "The wind picked up in the night and took the washing, two buckets and somebody's hat.", "Wiatr wzmógł się w nocy i zabrał pranie, dwa wiadra i czyjś kapelusz."),
    ("S", "*", "The wind off the water is strong enough to lean on, and the boats strain at their ropes.", "Wiatr znad wody jest na tyle silny, żeby się o niego oprzeć, a łodzie szarpią się na linach."),
]

