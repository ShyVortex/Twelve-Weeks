"""A-Life text pools, part D: the menu ticker.  Every row is ONE short sentence (<= ~110 characters) about a current fact of the clan's simulated life
(who is out on an expedition, who is hurt, what is being built, what each person is like).  Row format: see clan_alife_text_a.py.
The ticker pools are cycled per fact (several phrasings of the same fact come one after another, never the same twice in a row)."""

POOLS = {}

POOLS["f_exp"] = [
    ("*", "*", "{A}'s party is out at {dest} after {goal}, due back {nd_in}.", "Grupa, którą prowadzi {A}, jest {dest_at} po {goal_acc}; wróci {nd_in}."),
    ("*", "*", "{A} and {B} are somewhere near {dest}. Back {nd_in}, if the road allows.", "{A} i {B} są gdzieś w okolicy {dest_gen}. Wrócą {nd_in}, jeśli droga pozwoli."),
    ("*", "b", "{A} and {B} are still out at {dest}. {nd_in} is a long time to wait.", "{A} i {B} wciąż są {dest_at}. Powrót {nd_in} to długie czekanie."),
    ("*", "*", "The gate watch keeps an eye out for {A}'s party, due from {dest} {nd_in}.", "Warta przy bramie wypatruje grupy, którą prowadzi {A}; ma wrócić {dest_from} {nd_in}."),
]
POOLS["f_inj"] = [
    ("*", "*", "{A} has {inj} and is on light duty.", "{A} ma {inj_acc} i lekką służbę."),
    ("*", "*", "{A} is working around {inj}, and complaining about it.", "{A} pracuje mimo {inj_gen} i narzeka na to."),
    ("*", "n", "{A} has {inj}, and says it is nothing.", "{A} ma {inj_acc} i mówi, że to nic."),
    ("*", "g", "{A} jokes about {inj}, which means it is getting better.", "{A} żartuje na temat {inj_gen}, czyli jest coraz lepiej."),
]
POOLS["f_proj"] = [
    ("*", "*", "The work on {proj} is {prog}.", "Prace nad {proj_ins} {prog}."),
    ("*", "*", "{A} is working on {proj}. It is {prog}, they say.", "{A} pracuje nad {proj_ins}. Podobno prace {prog}."),
    ("*", "n", "{A} and {B} argue about {proj} again. The work is {prog}.", "{A} i {B} znów kłócą się o {proj_acc}. Prace {prog}."),
    ("*", "g", "{B} brings tea to whoever is working on {proj}.", "{B} nosi herbatę każdemu, kto pracuje nad {proj_ins}."),
]
POOLS["f_trade"] = [
    ("*", "*", "{grp} are expected at {dest} around day {due}.", "{grp_nom} mają się pojawić {dest_at} około dnia {due}."),
    ("*", "n", "{A} is putting together goods for {grp}, due at {dest} on day {due}.", "{A} zbiera towar dla {grp_gen}, którzy mają być {dest_at} w dniu {due}."),
    ("*", "*", "Everyone has an opinion about the trade with {grp} on day {due}.", "Każdy ma zdanie o wymianie z {grp_ins} w dniu {due}."),
]
POOLS["f_friend"] = [
    ("*", "*", "{A} and {B} are inseparable these days.", "{A} i {B} są ostatnio nierozłącz{AB?ni|ne}."),
    ("*", "g", "{A} and {B} laugh at jokes only the two of them find funny.", "{A} i {B} śmieją się z żartów, które śmieszą tylko ich dwoje."),
    ("*", "*", "{A} and {B} share a watch and a pot of tea.", "{A} i {B} dzielą wartę i dzbanek herbaty."),
    ("*", "n", "{B} saves {A} a place by the fire every night.", "{B} co wieczór zajmuje przy ogniu miejsce, które czeka na {A?niego|nią}: {A}."),
]
POOLS["f_rival"] = [
    ("*", "*", "{A} and {B} are not on speaking terms.", "{A} i {B} ze sobą nie rozmawiają."),
    ("*", "b", "{A} and {B} have started eating at opposite ends of the table.", "{A} i {B} zacz{AB?ęli|ęły} jeść na przeciwnych końcach stołu."),
    ("*", "*", "Whatever {A} says, {B} says the opposite, on principle.", "Cokolwiek mówi {A}, {B} mówi odwrotnie, z zasady."),
]
POOLS["f_romance"] = [
    ("*", "*", "{A} and {B} keep ending up on the same shift. Nobody mentions it.", "{A} i {B} ciągle trafiają na tę samą zmianę. Nikt o tym nie wspomina."),
    ("*", "g", "{A} and {B} walk the fence line together at dusk, slowly.", "{A} i {B} razem obchodzą o zmierzchu ogrodzenie, powoli."),
    ("*", "*", "{B} saves the better half of the bread for {A}.", "{B} odkłada lepszą połowę chleba, a dostaje ją {A}."),
]
POOLS["f_mentor"] = [
    ("*", "*", "{A} is teaching {B} to {skill}.", "{A} uczy, a {B} próbuje {skill}."),
    ("*", "*", "{B} is learning to {skill} from {A}, slowly.", "{B} uczy się powoli, jak {skill}; uczy {A}."),
    ("*", "g", "{B} can almost {skill} now. {A} will not say so yet.", "{B} prawie już potrafi {skill}. {A} jeszcze tego nie powie."),
]
POOLS["f_job"] = [
    ("*", "*", "Before the outbreak, {A} {job}.", "Przed epidemią {A} {job}."),
    ("*", "*", "{A} {job}, once. It shows in how {A_he} works.", "{A} kiedyś {job}. Widać to w pracy."),
    ("*", "*", "{A} never talks about the time {A_he} {job}.", "{A} nigdy nie mówi o czasach, gdy {A?on|ona} {job}."),
    ("*", "n", "People say {A} {job}, and that {A_he} was good at it.", "Ludzie mówią, że {A} {job} i że {A?był|była} w tym {A?dobry|dobra}."),
]
POOLS["f_origin"] = [
    ("*", "*", "{A} survived {orig} before joining the clan.", "{A} przetrwał{A?|a} {orig}, zanim dołączył{A?|a} do klanu."),
    ("*", "*", "{A} has been with the clan since day {jd}; before that, {orig}.", "{A} jest z klanem od dnia {jd}; wcześniej {orig}."),
    ("*", "n", "{A}: nobody asks about the time {orig}. Everybody wants to.", "{A}: nikt nie pyta, co było {orig}. Wszyscy by chcieli."),
]
POOLS["f_memorial"] = [
    ("*", "*", "{A} still keeps {D}'s {keep} where {A_he} can see it.", "{A} wciąż trzyma w zasięgu wzroku pamiątkę ({D}: {keep_nom})."),
    ("*", "b", "The place at the fire where {D} sat stays empty. {A} sits next to it.", "Miejsce przy ogniu, gdzie siadywał{D?|a} {D}, zostaje puste. {A} siada obok."),
    ("*", "*", "{A} mentions {D} at least once a day, and then looks surprised.", "Imię {D} pada codziennie; {A} wspomina o {D?nim|niej} i wygląda na zaskoczon{A?ego|ą}."),
]
POOLS["f_vigil"] = [
    ("*", "*", "{B} checks on {A} between shifts.", "{B} między zmianami zagląda, jak się czuje {A}."),
    ("*", "b", "{B} has not left {A}'s side all night.", "{B} przez całą noc nie odstępuje łóżka, na którym leży {A}."),
    ("*", "*", "{B} keeps the water for {A} fresh and the room warm.", "{B} dba, żeby woda była świeża, a w pokoju ciepło: {A} tego potrzebuje."),
    ("S", "*", "{B} prays quietly over {A} every evening.", "{B} co wieczór cicho się modli, a {A} słucha."),
]
POOLS["f_rat_good"] = [
    ("*", "g", "Supper is a little bigger than usual tonight, and nobody says why.", "Dzisiejsza kolacja jest trochę większa niż zwykle i nikt nie pyta dlaczego."),
    ("*", "g", "There is a small stock put by for the lean days, and everyone knows exactly where it is.", "Odłożono małe zapasy na chude dni i każdy wie dokładnie gdzie."),
    ("*", "n", "The pots are full, for now.", "Garnki są pełne, na razie."),
]
POOLS["f_rat_bad"] = [
    ("*", "b", "The portions are thinner every day, and everybody has stopped pretending not to notice.", "Porcje są z dnia na dzień cieńsze i wszyscy przestali udawać, że tego nie widzą."),
    ("*", "b", "Food is the only thing anyone talks about, and nobody talks about it loudly.", "O jedzeniu mówią wszyscy i nikt nie mówi o nim głośno."),
    ("*", "n", "The ladle goes round a little slower than it used to.", "Chochla krąży trochę wolniej niż dawniej."),
]
POOLS["f_season"] = [
    ("*", "*", "It is {season}, and the clan counts its days by the woodpile.", "Trwa {season}, a klan liczy dni stosem drewna."),
    ("*", "*", "Another day of {season} behind the walls.", "Kolejny dzień: {season}, za murami."),
    ("*", "n", "{season}: the clan has a coat for everyone, almost.", "{season}: klan ma płaszcz dla każdego, prawie."),
]
POOLS["f_count"] = [
    ("*", "*", "{size_ppl} sit down to supper tonight.", "Do kolacji siada dziś {size_ppl}."),
    ("*", "*", "{size_ppl} behind the walls, and one watch for all of them.", "{size_ppl} za murami i jedna warta dla wszystkich."),
]
# a persistent trait colours the person: row key = trait id (see clan_alife.TRAITS)
POOLS["f_trait:stubborn"] = [
    ("*", "*", "{A} will not be told twice, and will not be told once either.", "{A} nie da sobie tego powiedzieć dwa razy, ani nawet raz."),
    ("*", "*", "{A} digs in, as {A_he} always does.", "{A} się zapiera, jak zawsze."),
    ("*", "*", "Ask {A} to change {A_his} mind and watch the clan make bets.", "{A}: spróbuj namówić {A?go|ją} do zmiany zdania, a klan zacznie zawierać zakłady."),
]
POOLS["f_trait:joker"] = [
    ("*", "g", "{A} has a joke ready, as always. It is a bad one; the camp laughs.", "{A} ma gotowy żart, jak zawsze. Kiepski; obóz się śmieje."),
    ("*", "*", "{A} keeps the camp's spirits up with jokes nobody else could get away with.", "{A} podnosi obozowi morale żartami, na które nikt inny by sobie nie pozwolił."),
    ("*", "n", "{A} tells the one about the clicker and the cat again.", "{A} znów opowiada ten o klikaczu i kocie."),
]
POOLS["f_trait:quiet"] = [
    ("*", "*", "{A} says very little, and the clan listens when {A_he} does.", "{A} mówi bardzo mało, a klan słucha, kiedy już mówi."),
    ("*", "*", "{A} sits at the edge of the fire, listening.", "{A} siedzi na skraju ogniska i słucha."),
    ("*", "n", "Nobody remembers {A} ever raising {A_his} voice.", "Nikt nie pamięta, żeby {A} kiedykolwiek {A?podniósł|podniosła} głos."),
]
POOLS["f_trait:superstitious"] = [
    ("*", "*", "{A} knocks on wood before every patrol and will not say why.", "{A} stuka w drewno przed każdą wyprawą i nie powie dlaczego."),
    ("*", "*", "{A} will not walk under the washing line on a Tuesday.", "{A} nie przejdzie pod sznurem z praniem we wtorek."),
    ("*", "b", "{A} has stopped whistling after dark. It brings luck, {A_he} says.", "{A} przestał{A?|a} gwizdać po zmroku. Podobno przynosi pecha."),
]
POOLS["f_trait:generous"] = [
    ("*", "*", "{A} gives away half of {A_his} bread and calls it a bad appetite.", "{A} oddaje połowę swojego chleba i mówi, że nie ma apetytu."),
    ("*", "g", "{A} slips an extra spoon of stew into the smallest bowl, again.", "{A} znów dokłada łyżkę gulaszu do najmniejszej miski."),
    ("*", "*", "{A} always has something to spare, and never mentions it.", "{A} zawsze ma coś na zbyciu i nigdy o tym nie wspomina."),
]
POOLS["f_trait:hoarder"] = [
    ("*", "*", "{A} has a bag under the bunk nobody is allowed to look in.", "{A} ma pod pryczą torbę, do której nikomu nie wolno zaglądać."),
    ("*", "n", "{A} collects bottle caps, buttons and string, in case.", "{A} zbiera kapsle, guziki i sznurek, na wszelki wypadek."),
    ("*", "b", "{A} has started counting {A_his} own stash twice a day.", "{A} {A?zaczął|zaczęła} liczyć swoje zapasy dwa razy dziennie."),
]
POOLS["f_trait:hothead"] = [
    ("*", "*", "{A} is spoiling for an argument, and the camp is clearing out of the way.", "{A} szuka kłótni, a obóz usuwa się z drogi."),
    ("*", "*", "{A} slammed a door today. The door is fine; {A} is not.", "{A} {A?trzasnął|trzasnęła} dziś drzwiami. Drzwi są całe; {A} nie."),
    ("*", "n", "It takes very little to set {A} off, and everyone knows exactly how little.", "{A}: żeby wytrącić {A?go|ją} z równowagi, wystarczy tak niewiele, a wszyscy dokładnie wiedzą, jak niewiele."),
]
POOLS["f_trait:tinkerer"] = [
    ("*", "*", "{A} is taking something apart again, to see what is inside.", "{A} znów coś rozbiera, żeby zobaczyć, co jest w środku."),
    ("*", "g", "{A} fixed the squeaky gate with a spoon and a prayer.", "{A} naprawił{A?|a} skrzypiącą bramę łyżką i modlitwą."),
    ("*", "*", "Anything broken in the camp ends up on {A}'s workbench.", "Wszystko, co się zepsuje w obozie, trafia na warsztat, przy którym siedzi {A}."),
]
POOLS["f_trait:storyteller"] = [
    ("*", "g", "{A} tells a story by the fire, and for an hour nobody is hungry.", "{A} opowiada historię przy ogniu i przez godzinę nikt nie jest głodny."),
    ("*", "*", "Every story {A} tells gets a little bigger with each telling.", "Każda historia, którą opowiada {A}, rośnie z każdym opowiedzeniem."),
    ("*", "n", "{A} is on the fourth version of the story about the bridge.", "{A} jest na czwartej wersji historii o moście."),
]
POOLS["f_trait:nervous"] = [
    ("*", "*", "{A} jumps at every noise, and is right about one in ten.", "{A} podskakuje przy każdym hałasie i ma rację co dziesiąty raz."),
    ("*", "b", "{A} has not slept properly in days, and keeps checking the lock.", "{A} od dni nie spał{A?|a} porządnie i ciągle sprawdza zamek."),
    ("*", "*", "{A} checks the lock three times and hopes nobody noticed.", "{A} sprawdza zamek trzy razy i ma nadzieję, że nikt nie zauważył."),
]
POOLS["f_trait:optimist"] = [
    ("*", "g", "{A} says tomorrow will be better, and today it almost sounds true.", "{A} mówi, że jutro będzie lepiej, a dziś brzmi to prawie prawdziwie."),
    ("*", "*", "{A} always finds the one good thing in the day, even when it is a small one.", "{A} zawsze znajduje jedną dobrą rzecz w dniu, nawet gdy jest mała."),
    ("*", "b", "{A} is the only one still singing, and nobody has the heart to stop {A_him}.", "{A} jako jedyn{A?y|a} wciąż śpiewa i nikt nie ma serca tego przerwać."),
]
POOLS["f_trait:grumbler"] = [
    ("*", "*", "{A} has a complaint about the soup, the weather and the war, in that order.", "{A} ma zażalenie na zupę, pogodę i wojnę, w tej kolejności."),
    ("*", "n", "{A} grumbles all through the watch, and does it well.", "{A} narzeka przez całą wartę i robi to dobrze."),
    ("*", "g", "{A} complains that the weather is too nice, and means it.", "{A} narzeka, że pogoda jest zbyt ładna, i mówi to poważnie."),
]
# a role colours the person too
POOLS["f_role"] = [
    ("*", "*", "{A}, the {A_role}, is busy with the day's work.", "{A}, {A_role}, jest zajęt{A?y|a} dzisiejszą pracą."),
    ("*", "*", "Ask {A}, the {A_role}; {A_he} will know.", "{A}, {A_role}, {A?będzie wiedział|będzie wiedziała}, jeśli ktoś czegoś nie wie."),
]
