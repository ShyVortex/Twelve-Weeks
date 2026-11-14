"""Clan feed lines for the SMALL clans (a clan of ONE survivor got "Ingrid isn't talking. We're watching her." and "Nobody's laughing at
dinner" - there is no "we", and nobody to watch her).  The narrator's voice follows the clan's size:

  3+ alive   the existing group pools (clan_story_lines_*.py)
  2 alive    "we" is fine, crowd words are not (everyone, nobody, the kids, the camp ...): group lines are filtered with CROWD_RE, plus the DUO pools here
  1 alive    the narrator IS the survivor: first person singular, diary voice, never we / us / our / nobody / everyone, never third person about the
             survivor; only the SOLO pools here are used (kinds without a solo pool are simply not written)

Every line carries both languages side by side (English, Polish) so the pair cannot drift: ROWS = [(pool, scope, english, polish)] feeds the
language registry in clan_story_pl.py.  The narrator is always {A} (gender for the Polish first person: {A?łem|łam}); {D} is a dead member,
{B} the other survivor of a duo.  Scope: "*" both factions, "W" Wolves, "S" Seraphites.
"""
import re


def X(en, pl): return ("*", en, pl)
def W(en, pl): return ("W", en, pl)
def S(en, pl): return ("S", en, pl)


# words of a crowd: never in a clan of two or one
CROWD_RE = re.compile(r"\b(everyone|everybody|nobody|no one|kids?|children|others|the camp|whole camp|half the camp|crowd|the rest|all of us|folks|our young|the young|young ones|little ones|the faithful)\b", re.I)
# the plural voice: never in a clan of one
GROUP_RE = re.compile(r"\b(we|we're|we've|we'll|we'd|us|our|ours|ourselves|nobody|everyone|everybody|no one|the others|others|kids?|children|the camp|crowd|the rest|our young|the young|young ones|little ones|the faithful)\b", re.I)

DEFS = {}

DEFS["hunger"] = [
    X("Hungry again. I split what was left in two and ate one half. The other half is tomorrow's.",
      "Znowu {A?głodny|głodna}. Podzieli{A?łem|łam} resztki na pół i zjad{A?łem|łam} jedną połowę. Druga jest na jutro."),
    X("I counted the cans twice. Same number both times. It doesn't get bigger when you check.",
      "Przeliczy{A?łem|łam} puszki dwa razy. Za każdym razem tyle samo. Nie przybywa od patrzenia."),
    X("My stomach has been growling since dawn. I keep telling it there's nothing to give.",
      "Od świtu burczy mi w brzuchu. Wciąż mu powtarzam, że nie mam co dać."),
    X("Water, a few crumbs, and the hope that tomorrow's better. That was dinner.",
      "Woda, kilka okruchów i nadzieja, że jutro będzie lepiej. Tyle było na kolację."),
    X("Hunger makes the quiet louder. I ate slowly just to have something to do.",
      "Głód sprawia, że cisza jest głośniejsza. Jad{A?łem|łam} powoli, żeby mieć coś do roboty."),
    X("I went through every bag twice looking for something I missed. I hadn't missed anything.",
      "Przeszuka{A?łem|łam} wszystkie torby dwa razy, szukając czegoś, co umknęło mojej uwadze. Niczego nie przeoczy{A?łem|łam}."),
]
DEFS["starving"] = [
    X("I can't remember the last real meal. I can remember the smell of it, which is worse.",
      "Nie pamiętam ostatniego prawdziwego posiłku. Pamiętam jego zapach, a to gorsze."),
    X("My hands shake when I try to work. I sit down more often now, and stand up slower.",
      "Ręce mi się trzęsą, kiedy próbuję pracować. Siadam coraz częściej, wstaję coraz wolniej."),
    X("I boiled a leather strap today and chewed it for an hour. I'm not proud of it. I'd do it again.",
      "Ugotowa{A?łem|łam} dziś skórzany rzemień i żu{A?łem|łam} go przez godzinę. Nie jestem z tego dumn{A?y|a}. Zrobi{A?łbym|łabym} to znowu."),
    X("Day {day}, and I'm starving. Not the figure-of-speech kind. The kind where the room tilts.",
      "Dzień {day}, a ja umieram z głodu. Nie w przenośni. Tak, że pokój się przechyla."),
    X("I keep thinking about food and I keep trying to stop. Neither is working.",
      "Ciągle myślę o jedzeniu i ciągle próbuję przestać. Nic z tego."),
    X("I can feel my ribs through my jacket. Another notch in the belt. I'm running out of belt.",
      "Czuję żebra przez kurtkę. Kolejna dziurka w pasku. Kończy mi się pasek."),
]
DEFS["sick"] = [
    X("I've got {ill_a}. I said it out loud just to hear a voice.",
      "Mam {ill_acc}. Powiedzia{A?łem|łam} to na głos, żeby usłyszeć choć jakiś głos."),
    X("Mornings are the worst with {ill_a}. I lie there until I can talk my legs into it.",
      "Rano z {ill_ins} jest najgorzej. Leżę, dopóki nie przekonam nóg."),
    X("I know what would help: {cure}. I also know I won't find it here.",
      "Wiem, co by pomogło: {cure}. Wiem też, że tu tego nie znajdę."),
    X("Cold sweat, bad dreams, and a long list of things I won't be able to do tomorrow.",
      "Zimny pot, złe sny i długa lista rzeczy, których jutro nie zrobię."),
    X("I keep my own watch now. If I'm going down, I want to be awake for it.",
      "Pilnuję teraz {A?samego|samej} siebie. Jeśli mam upaść, chcę być przy tym {A?przytomny|przytomna}."),
    X("I write down my symptoms so someone could read them later. I try not to think about who.",
      "Zapisuję objawy, żeby ktoś mógł je kiedyś przeczytać. Staram się nie myśleć o tym, kto."),
]
DEFS["worse"] = [
    X("It's worse today. I tried to stand and the floor had other plans.",
      "Dziś jest gorzej. Spróbowa{A?łem|łam} wstać, a podłoga miała inne plany."),
    X("I can feel {ill_a} settling in for good. I'm trying not to listen.",
      "Czuję, jak {ill} rozgaszcza się na dobre. Staram się nie słuchać."),
    X("My hands won't stop shaking. I can't tell if it's the sickness or the fear.",
      "Ręce nie przestają mi drżeć. Nie wiem, czy to choroba, czy strach."),
]
DEFS["medicine"] = [
    X("Not a trace of {cure}. I went through every shelf in the {place}.",
      "Ani śladu {cure_gen}. Przeszuka{A?łem|łam} każdą półkę {place_at}."),
    X("I'd trade everything I own for {cure}. It isn't much, but it's everything.",
      "Oddał{A?bym|abym} wszystko, co mam, za {cure_acc}. To niewiele, ale to wszystko."),
    X("I keep going on cold water and bad jokes. Mostly the water.",
      "Trzymam się dzięki zimnej wodzie i kiepskim żartom. Głównie wodzie."),
]
DEFS["recovery"] = [
    X("I woke up and the worst was over. I sat in the doorway for an hour just breathing.",
      "Obudzi{A?łem|łam} się i najgorsze minęło. Przesiedzia{A?łem|łam} godzinę w drzwiach, po prostu oddychając."),
    X("I'm on my feet again. Slow, with a lot of resting, but on my feet.",
      "Znów stoję na nogach. Powoli i z częstymi przerwami, ale stoję."),
    X("Beat it. Alone. Somehow that feels like it should count double.",
      "Pokona{A?łem|łam} to. Sam{A?|a}. Jakoś wydaje mi się, że powinno się to liczyć podwójnie."),
]
DEFS["grief"] = [
    X("I still set out two cups in the morning. Then I remember {D} and put one back.",
      "Wciąż rano wyjmuję dwa kubki. Potem przypominam sobie {D} i odkładam jeden."),
    X("I talk to {D} sometimes. {D_He} never interrupts. That's the worst part.",
      "{D}: czasem rozmawiam z {D?nim|nią}. {D?On|Ona} nigdy nie przerywa. To najgorsze."),
    X("Found {D_his} jacket on the hook today and put it on. It still smells like {D_him}.",
      "{D}: znalaz{A?łem|łam} dziś {D?jego|jej} kurtkę na haku i założy{A?łem|łam} ją. Wciąż {D?nim|nią} pachnie."),
    X("Day {day}. I said {D}'s name out loud so it wouldn't go quiet in here.",
      "Dzień {day}. Powiedzia{A?łem|łam} głośno: {D}, żeby to imię nie zamilkło."),
    X("I keep turning to say something to {D}. Habit is a cruel thing.",
      "{D}: wciąż odwracam się, żeby coś {D?mu|jej} powiedzieć. Przyzwyczajenie bywa okrutne."),
    X("I wonder what {D} would have said about how I'm doing. Something kind. Something that made me laugh.",
      "Ciekawe, co by o tym powiedzia{D?ł|ła} {D}. Pewnie coś miłego. Pewnie coś, co by mnie rozśmieszyło."),
]
DEFS["grief:illness"] = [
    X("I can still hear {D} coughing sometimes, in the quiet. It isn't there. I listen anyway.",
      "Czasem w ciszy wciąż słyszę, jak {D} kaszle. To tylko złudzenie. I tak nasłuchuję."),
    X("I keep the blanket {D} used folded by the door. Silly. It's just a blanket.",
      "Koc, którego używa{D?ł|ła} {D}, wciąż leży złożony przy drzwiach. Głupie. To tylko koc."),
    X("Sickness took {D} slowly. I'd give a lot for one more bad day with {D_him} instead of none.",
      "{D}: choroba zabierała {D?go|ją} powoli. Oddał{A?bym|abym} wiele za jeszcze jeden zły dzień z {D?nim|nią}, zamiast żadnego."),
]
DEFS["grief:starved"] = [
    X("{D} went without so I could eat. I know that now. I wish I'd known then.",
      "{D} {D?głodował|głodowała}, żebym {A?mógł|mogła} jeść. Wiem to teraz. Chcia{A?łbym|łabym} wiedzieć to wtedy."),
    X("I counted the last cans at {D}'s bedside. It wasn't enough. It was never going to be.",
      "{D}: przeliczy{A?łem|łam} ostatnie puszki przy {D?jego|jej} łóżku. To nie wystarczyło. Nigdy nie miało wystarczyć."),
    X("Every time I eat now I think of {D}. I eat anyway. {D_He} would have wanted that.",
      "{D}: za każdym razem, gdy jem, myślę o {D?nim|niej}. I tak jem. Tego {D?chciałby|chciałaby}."),
]
DEFS["grief:attack"] = [
    X("I keep seeing {D} at the fence, back to me, facing them. That's how I'll remember it.",
      "{D}: wciąż widzę {D?go|ją} przy ogrodzeniu, plecami do mnie, twarzą do nich. Tak to zapamiętam."),
    X("{D} bought me the time to run. I ran. I haven't forgiven myself for that.",
      "{D} kupi{D?ł|ła} mi czas na ucieczkę. Uciek{A?łem|łam}. Nie wybaczy{A?łem|łam} sobie tego."),
    X("The {enemies} didn't just take {D}. They took the only person who knew my stories.",
      "{D}: {enemies} nie zabrały tylko {D?jego|jej}. Zabrały jedyną osobę, która znała moje historie."),
]
DEFS["grief:lost"] = [
    X("I keep leaving a light on for {D}. I know. I leave it on anyway.",
      "{D}: wciąż zostawiam światło dla {D?niego|niej}. Wiem. I tak je zostawiam."),
    X("{D} could be anywhere. Alive, even. I hold on to 'even'.",
      "{D} może być wszędzie. Nawet żyć. Trzymam się tego „nawet”."),
    X("I look down the road a lot, in case it's {D}. It's never {D}. I look anyway.",
      "Często patrzę na drogę, czy nie idzie {D}. To nigdy nie jest {D}. I tak patrzę."),
]
DEFS["grief_mercy"] = [
    X("I did what {D} asked. It was right. It's still the heaviest thing I carry.",
      "Zrobi{A?łem|łam}, o co prosi{D?ł|ła} {D}. To było słuszne. Wciąż to najcięższe, co niosę."),
    X("{D} thanked me, at the end. I'd give anything to un-hear that.",
      "{D} podziękowa{D?ł|ła} mi na końcu. Oddał{A?bym|abym} wszystko, żeby tego nie słyszeć."),
    X("Mercy shouldn't weigh this much. {D} is at rest, and I am not.",
      "Miłosierdzie nie powinno tyle ważyć. {D} odpoczywa, a ja nie."),
]
DEFS["guilt"] = [
    X("I keep going over it. If I'd been faster, {D} would still be here. I know that isn't true. I go over it anyway.",
      "Wciąż to analizuję. Gdybym {A?był szybszy|była szybsza}, {D} wciąż by tu {D?był|była}. Wiem, że to nieprawda. I tak analizuję."),
    X("{D}'s things are still where {D_he} left them. I can't move them and I can't stop looking.",
      "{D}: {D?jego|jej} rzeczy wciąż leżą tam, gdzie zostały. Nie mogę ich ruszyć i nie mogę przestać patrzeć."),
    X("I made a choice and {D} paid for it. That's the sentence I wake up with.",
      "Dokona{A?łem|łam} wyboru, a {D} za to zapłaci{D?ł|ła}. Z tym zdaniem się budzę."),
]
DEFS["despair"] = [
    X("Day {day}. I stopped counting the good ones. I only count how many are left to get through.",
      "Dzień {day}. Przesta{A?łem|łam} liczyć te dobre. Liczę tylko, ile jeszcze trzeba przetrwać."),
    X("I haven't spoken out loud in days. My voice cracked when I tried. I think I frightened myself.",
      "Od kilku dni nie odezwa{A?łem|łam} się na głos. Głos mi się załamał, kiedy spróbowa{A?łem|łam}. Chyba sam{A?|a} się wystraszy{A?łem|łam}."),
    X("There's a point where tired stops being a feeling and becomes a place. I live there now.",
      "Jest taki moment, kiedy zmęczenie przestaje być uczuciem i staje się miejscem. Tam teraz mieszkam."),
    X("I thought about walking out the gate and just continuing. Then I thought: who closes it behind me?",
      "Myśla{A?łem|łam}, żeby wyjść za bramę i po prostu iść dalej. Potem pomyśla{A?łem|łam}: kto zamknie ją za mną?"),
    X("I don't cry anymore. It stopped working. I just sit, and the hours pass over me.",
      "Już nie płaczę. Przestało działać. Po prostu siedzę, a godziny przechodzą ponad mną."),
]
DEFS["hope"] = [
    X("Woke up to a clear sky and a quiet horizon. Day {day} and I'm still breathing. Today feels possible.",
      "Obudzi{A?łem|łam} się pod czystym niebem i spokojnym horyzontem. Dzień {day}, a ja wciąż oddycham. Dziś wydaje się możliwe."),
    X("I fixed the roof today. It's not much, but it's mine, and it doesn't leak.",
      "Naprawi{A?łem|łam} dziś dach. To niewiele, ale mój i nie przecieka."),
    X("Somebody will come. Somebody always does. I'm keeping the fire lit so they can find it.",
      "Ktoś przyjdzie. Ktoś zawsze przychodzi. Podtrzymuję ogień, żeby mógł go znaleźć."),
    X("I found a seed packet in a coat pocket. Tomatoes. I planted every one of them.",
      "Znalaz{A?łem|łam} w kieszeni płaszcza paczkę nasion. Pomidory. Posadzi{A?łem|łam} każde z nich."),
    X("I laughed today. Out loud, at nothing. Then I sat quietly and let it be okay that I did.",
      "Dziś się roześmia{A?łem|łam}. Na głos, bez powodu. Potem siedzia{A?łem|łam} cicho i pozwoli{A?łem|łam}, żeby to było w porządku."),
]
DEFS["hope_after"] = [
    X("{D} would have liked today. Sun, a full pot, a quiet gate. I told {D_him} about it anyway.",
      "{D} {D?byłby|byłaby} zadowolon{D?y|a} z dzisiejszego dnia. Słońce, pełny garnek, cicha brama. I tak {D?mu|jej} o tym opowiedzia{A?łem|łam}."),
    X("I ate a proper meal tonight and thought of {D} the whole time. It felt less like betrayal than I expected.",
      "{D}: cały czas o {D?nim|niej} myśla{A?łem|łam}, jedząc dziś porządny posiłek. To było mniej podobne do zdrady, niż się spodziewa{A?łem|łam}."),
    X("Better days, finally. {D} always said they'd come back. I'd like {D_him} to know {D_he} was right.",
      "W końcu lepsze dni. {D} zawsze mówi{D?ł|ła}, że wrócą. Chcia{A?łbym|łabym}, żeby {D?wiedział|wiedziała}, że {D?miał|miała} rację."),
]
DEFS["plenty"] = [
    X("A full pot tonight. I ate until I couldn't move and I regret nothing.",
      "Pełny garnek na wieczór. Jad{A?łem|łam}, aż nie mog{A?łem|łam} się ruszyć, i niczego nie żałuję."),
    X("More supplies than I can use. Strange problem to have, and I'll take it.",
      "Więcej zapasów, niż jestem w stanie zużyć. Dziwny problem, ale chętnie go przyjmę."),
    X("I made enough for two, out of habit. Ate it all anyway. Day {day}.",
      "Z przyzwyczajenia ugotowa{A?łem|łam} na dwoje. I tak zjad{A?łem|łam} wszystko. Dzień {day}."),
]
DEFS["calm"] = [
    X("Quiet day. I mended, I cooked, I listened. The only voice in the house was mine.",
      "Spokojny dzień. Łata{A?łem|łam}, gotowa{A?łem|łam}, nasłuchiwa{A?łem|łam}. Jedynym głosem w domu był mój."),
    X("I keep catching myself waiting for an answer.",
      "Wciąż łapię się na tym, że czekam na odpowiedź."),
    X("The same routine again: water, fence, food, sleep. Routine is the only company I've got.",
      "Znowu ten sam rytm: woda, ogrodzenie, jedzenie, sen. Rutyna to jedyne towarzystwo, jakie mam."),
    X("I set my watch by the sun now. It's the only thing that still keeps appointments.",
      "Czas mierzę teraz słońcem. Tylko ono jeszcze dotrzymuje terminów."),
    X("Day {day}. I'm still here. It's not a lot to write, but it's true.",
      "Dzień {day}. Wciąż tu jestem. To niewiele do zapisania, ale to prawda."),
    X("I read the same three pages of an old book again. They've started to feel like friends.",
      "Znów przeczyta{A?łem|łam} te same trzy strony starej książki. Zaczynają przypominać przyjaciół."),
    X("The silence isn't empty. It's full of the people who used to be here.",
      "Cisza nie jest pusta. Jest pełna ludzi, którzy tu kiedyś byli."),
    X("I talked to the stove today. It listened better than most.",
      "Rozmawia{A?łem|łam} dziś z piecem. Słuchał lepiej niż większość."),
    W("From the roof of the {place} I watched Seattle go dark, block by block. Somewhere out there the WLF is still standing, I tell myself.",
      "Z dachu {place_gen} patrzy{A?łem|łam}, jak Seattle ciemnieje, kwartał po kwartale. Gdzieś tam WLF wciąż stoi, powtarzam sobie."),
    W("I walked the patrol route around the {place} alone. One set of footsteps sounds a lot smaller than I remember.",
      "{A?Obszedłem|Obeszłam} trasę patrolu wokół {place_gen} samotnie. Jedne kroki brzmią o wiele ciszej, niż pamiętam."),
    W("Isaac's last order is still pinned up in the {place}: hold the line. So I hold it. One person is also a line.",
      "Ostatni rozkaz Isaaca wciąż wisi {place_at}: utrzymać linię. Więc ją utrzymuję. Jedna osoba to też linia."),
    W("I hold the radio to my ear every night. Static, static, and then, once in a while, a voice from far away.",
      "Co noc przykładam radio do ucha. Szum, szum, a czasem głos z daleka."),
    W("I stand under the old stadium lights sometimes. They haven't worked in years. I stand there anyway.",
      "Czasem stoję pod starymi reflektorami stadionu. Nie działają od lat. I tak tam stoję."),
    W("I cleaned my rifle for the third time today. Not for any reason. It just has a right way to be done.",
      "Wyczyści{A?łem|łam} dziś karabin po raz trzeci. Bez powodu. Po prostu istnieje właściwy sposób, żeby to robić."),
    W("The {enemies} are out there, and I'm one person. They don't know yet. Or maybe they do. I keep the lights low.",
      "{enemies} są tam gdzieś, a ja jestem jedną osobą. Jeszcze nie wiedzą. A może wiedzą. Przygaszam światło."),
    W("Seattle used to have a skyline. I tell myself I can still see it from the {place} when the fog lifts.",
      "Seattle miało kiedyś panoramę miasta. Wmawiam sobie, że widzę ją jeszcze {place_from}, gdy mgła się unosi."),
    S("I walked the shore at dawn and said the old words alone. The Light doesn't need an audience, they say. I'm testing that.",
      "O świcie {A?szedłem|szłam} brzegiem i sam{A?|a} wypowiedzia{A?łem|łam} stare słowa. Światło nie potrzebuje publiczności, mówią. Sprawdzam to."),
    S("The Prophet's words are written on the wall of the long house. I read them aloud every evening, mostly for the sound.",
      "Słowa Prorokini są wypisane na ścianie długiego domu. Czytam je codziennie wieczorem na głos, głównie dla samego dźwięku."),
    S("I lit a candle for the Elders. I don't know if they're alive. Lighting it was my way of insisting they are.",
      "Zapali{A?łem|łam} świecę za Starszych. Nie wiem, czy żyją. Zapalenie jej to mój sposób, żeby upierać się, że tak."),
    S("The island feels bigger with one person on it. Every path I walk, I walk alone. The trees don't mind.",
      "Wyspa wydaje się większa, gdy jest na niej jedna osoba. Każdą ścieżką idę sam{A?|a}. Drzewom to nie przeszkadza."),
    S("I wove for hours today, like the weavers do. Mine is crooked, but it holds. Everything crooked can hold, I'm learning.",
      "Tka{A?łem|łam} dziś przez kilka godzin, tak jak robią to tkacze. Mój jest krzywy, ale się trzyma. Uczę się, że wszystko, co krzywe, może wytrzymać."),
    S("The Light is a long way off today, and I'm a long way down. I keep walking toward it, one foot at a time.",
      "Światło jest dziś daleko, a ja jestem głęboko w dole. Idę ku niemu, krok po kroku."),
    S("From the harbor I watched the water for sails. Nothing but gulls. I stayed until the tide went out.",
      "Z przystani wypatrywa{A?łem|łam} żagli. Tylko mewy. Zosta{A?łem|łam}, aż woda opadła."),
    S("The Prophet taught that the Light finds anyone who keeps still long enough. I'm keeping very still.",
      "Prorokini nauczała, że Światło znajdzie każdego, kto wystarczająco długo trwa w bezruchu. Trwam w całkowitym bezruchu."),
]
DEFS["event_warn"] = [
    X("Tomorrow they come. I've reinforced what I can. One person doesn't make much of a wall.",
      "Jutro przyjdą. Wzmocni{A?łem|łam}, co się dało. Jedna osoba to niezbyt mocny mur."),
    W("The {enemies} are coming for the {place}. I sharpened everything that cuts and sat down facing the door.",
      "{enemies} idą {place_to}. Naostrzy{A?łem|łam} wszystko, co tnie, i usiad{A?łem|łam} twarzą do drzwi."),
    S("The {enemies} will come soon. I said the old words, strung my bow and sat facing the shore.",
      "{enemies} wkrótce przyjdą. Powtórzy{A?łem|łam} stare słowa, napi{A?ąłem|ęłam} łuk i usiad{A?łem|łam} twarzą do brzegu."),
]
DEFS["event_hold"] = [
    X("They came, and they left. I'm bleeding in two places and the gate still stands. I count that as a win.",
      "Przyszli i odeszli. Krwawię w dwóch miejscach, a brama wciąż stoi. Liczę to jako wygraną."),
    X("I held. One person, one gate, one long night. I'm going to sleep for a week.",
      "Utrzyma{A?łem|łam} się. Jeden człowiek, jedna brama, jedna długa noc. Prześpię cały tydzień."),
]
DEFS["event_heavy"] = [
    X("I held, but it cost me. Everything I couldn't carry away, I lost.",
      "Obroni{A?łem|łam} się, ale drogo mnie to kosztowało. Wszystko, czego nie dało się unieść, przepadło."),
    X("The attack is over. The {place} is a mess, and so am I. Tomorrow I'll start fixing one of those.",
      "Atak się skończył. {place_at} bałagan, ja też jestem w rozsypce. Jutro zacznę naprawiać jedno z dwojga."),
]
DEFS["event_massacre"] = [
    X("It was a slaughter. I ran, and I'm not going to apologise for it.",
      "To była rzeź. Uciek{A?łem|łam}, i nie zamierzam za to przepraszać."),
    X("The {enemies} took {lost} from me in one night. I'm still counting the faces.",
      "{enemies} zabrały mi {lost_acc} w jedną noc. Wciąż liczę twarze."),
]
DEFS["event_nojoin"] = [
    X("I watched the road all day. It stayed empty.",
      "Cały dzień wpatrywa{A?łem|łam} się w drogę. Pozostała pusta."),
    X("I left food by the gate in case someone wandered in. The birds got it.",
      "Zostawi{A?łem|łam} jedzenie przy bramie, gdyby ktoś się przybłąkał. Zjadły je ptaki."),
]
DEFS["clan_won"] = [
    X("I made it. Just me, but I made it.",
      "Udało mi się. Tylko mnie, ale się udało."),
    X("Day {day}. Alone, hungry and still here. I'll take it as a win.",
      "Dzień {day}. Sam{A?|a}, {A?głodny|głodna} i wciąż tu. Uznaję to za zwycięstwo."),
]
DEFS["death_illness"] = [
    X("{D} didn't make it through the night. I held {D_his} hand until it was just a hand. I'm the only one left.",
      "{D} nie przetrwa{D?ł|ła} nocy. Trzyma{A?łem|łam} {D?go|ją} za rękę, aż została tylko ręka. Zosta{A?łem|łam} tu {A?sam|sama}."),
    X("{D} stopped coughing sometime before dawn. The quiet was worse than the coughing. Now it's only me.",
      "{D} przesta{D?ł|ła} kaszleć przed świtem. Cisza była gorsza niż kaszel. Teraz jestem tylko ja."),
]
DEFS["death_mercy"] = [
    X("{D} asked me to end it. I did what I was asked. I carry that by myself now.",
      "{D} poprosi{D?ł|ła}, żebym z tym skończy{A?ł|ła}. Zrobi{A?łem|łam}, o co {D?prosił|prosiła}. Teraz niosę to sam{A?|a}."),
    X("It was the kind thing, and it was the hardest thing. {D} is out of pain, and I'm the last one standing.",
      "To był akt łaski i najtrudniejsza rzecz w życiu. {D} już nie cierpi, a ja zosta{A?łem|łam} sam{A?|a}."),
]
DEFS["death_starved"] = [
    X("{D} starved. I had a crust in my pocket I'd forgotten about. That's what I'll remember.",
      "{D} umar{D?ł|ła} z głodu. Mia{A?łem|łam} w kieszeni skórkę chleba, o której zapomnia{A?łem|łam}. To zapamiętam."),
    X("There wasn't enough, and {D} told me to eat it. I did. That's the part I can't forgive.",
      "Było za mało i {D} kaza{D?ł|ła} mi to zjeść. Zjad{A?łem|łam}. Tego nie potrafię sobie wybaczyć."),
]
DEFS["death_lost"] = [
    X("{D} went out and never came back. I waited at the gate until the light went. Then I waited some more.",
      "{D} {D?wyszedł|wyszła} i nie wróci{D?ł|ła}. Czeka{A?łem|łam} przy bramie, aż zgasło światło. Potem czeka{A?łem|łam} dalej."),
    X("{D} didn't come back from the {place}. I still keep the door unlocked. It's all there is left to do.",
      "{D} nie wróci{D?ł|ła} {place_from}. Wciąż nie zamykam drzwi. Tylko to mi zostało."),
]
DEFS["death_walkout"] = [
    X("{D} walked out and told me not to follow. I haven't. I'm still deciding if that was loyalty or fear.",
      "{D} {D?odszedł|odeszła} i kaza{D?ł|ła} mi nie iść za sobą. Nie {A?poszedłem|poszłam}. Wciąż nie wiem, czy to była lojalność, czy strach."),
    X("{D} left in the night. No note. I read the empty bed like it was one.",
      "{D} {D?odszedł|odeszła} w nocy. Bez listu. Czytam puste posłanie, jakby nim był."),
]
DEFS["death_suicide"] = [
    X("{D} is gone. I won't write how. I just keep wishing I had sat up one more night.",
      "{D} nie żyje. Nie napiszę, jak. Żałuję tylko, że nie posiedzia{A?łem|łam} przy {D?nim|niej} jeszcze jednej nocy."),
    X("{D}: I'm angry at you, and at myself. Mostly I'm just tired, and the house is very quiet.",
      "{D}: jestem na ciebie zł{A?y|a}, i na siebie. Głównie jestem po prostu zmęczon{A?y|a}, a w domu panuje cisza."),
]
DEFS["death_bite"] = [
    X("{D} was bitten {ago}. I did what had to be done, and I'm not going to write down how it felt.",
      "{D} {D?został|została} ugryzion{D?y|a} {ago}. Zrobi{A?łem|łam}, co trzeba było zrobić, i nie napiszę, jak się z tym czuję."),
    X("I keep checking my own arms for marks. {D} was bitten {ago}. I'm fine. I'm fine.",
      "Ciągle sprawdzam własne ręce, czy nie mam śladów. {D} {D?został|została} ugryzion{D?y|a} {ago}. Nic mi nie jest. Nic mi nie jest."),
]
DEFS["death_attack"] = [
    X("{D} went down in the attack. I dragged {D_him} back as far as I could. It wasn't far enough.",
      "{D} {D?padł|padła} podczas ataku. Odciągn{A?ąłem|ęłam} {D?go|ją} tak daleko, jak się dało. To było za mało."),
    X("The {enemies} took {D}. I'm still here. I keep waiting to feel like that was luck.",
      "{D}: {enemies} zabrały {D?go|ją}. Ja wciąż tu jestem. Czekam, aż poczuję, że to było szczęście."),
]
DEFS["death_attack_many"] = [
    X("I lost {lost} in the attack. I walked away. I still don't know why.",
      "W ataku straci{A?łem|łam} {lost_acc}. Ja {A?wyszedłem|wyszłam} z tego cało. Wciąż nie wiem, dlaczego."),
    X("In one night the {enemies} took {lost}. I'm the one they missed.",
      "W jedną noc {enemies} zabrały {lost_acc}. Mnie ominęły."),
]
DEFS["loss_many"] = [
    X("I lost {lost} in a handful of days. I stopped counting, then started again. It's only me now.",
      "Straci{A?łem|łam} {lost_acc} w ciągu kilku dni. Przesta{A?łem|łam} liczyć, potem zacz{A?ąłem|ęłam} od nowa. Teraz jestem tylko ja."),
    X("Hunger, sickness, grief, it all runs together now. {lost} gone. I'm what's left.",
      "Głód, choroba, żałoba, wszystko się zlewa. Straci{A?łem|łam} {lost_acc}. Zosta{A?łem|łam} tylko ja."),
]
DEFS["t_h"] = [
    X("I caught a rabbit.", "Złapa{A?łem|łam} królika."),
    X("I'm learning to sew.", "Uczę się szyć."),
    X("I'm repairing the fence. All of it.", "Naprawiam ogrodzenie. Całe."),
    X("I caught a fish.", "Złowi{A?łem|łam} rybę."),
    X("I'm skinning a deer.", "Oprawiam jelenia."),
    X("I'm fetching water.", "Noszę wodę."),
    X("I'm working in the garden.", "Pracuję w ogrodzie."),
    X("I'm planting kale in the garden.", "Sadzę jarmuż w ogrodzie."),
    X("I'm pulling weeds in the garden.", "Pielę chwasty w ogrodzie."),
    X("I'm mending clothes.", "Łatam ubrania."),
    X("I'm washing clothes.", "Piorę ubrania."),
    X("I'm taking inventory. It's a short list.", "Robię inwentaryzację. To krótka lista."),
    X("I'm collecting wood for the fire.", "Zbieram drewno na ogień."),
    X("I went foraging.", "{A?Poszedłem|Poszłam} zbierać jedzenie."),
    X("I went fishing.", "{A?Poszedłem|Poszłam} na ryby."),
    X("I found some old books.", "Znalaz{A?łem|łam} kilka starych książek."),
    X("I'm sharpening arrows.", "Ostrzę strzały."),
    X("I'm setting rabbit traps.", "Zastawiam sidła na króliki."),
    X("I'm smoking some meat.", "Wędzę mięso."),
    X("I'm making a map of the area.", "Rysuję mapę okolicy."),
    X("I'm pickling vegetables.", "Kiszę warzywa."),
    X("I'm reading an old book. Out loud, for the company.", "Czytam starą książkę. Na głos, dla towarzystwa."),
    X("I'm building a chicken coop.", "Buduję kurnik."),
    X("I'm starting a fire for dinner.", "Rozpalam ogień na kolację."),
    X("I'm healthy. Tired, but healthy.", "Jestem zdrow{A?y|a}. Zmęczon{A?y|a}, ale zdrow{A?y|a}."),
    X("I'm doing a shift in the lookout. It's every shift.", "Stoję na zmianie w punkcie obserwacyjnym. Na każdej."),
    X("I'm repairing the water collector.", "Naprawiam zbiornik na wodę."),
    X("I'm trying to sleep.", "Próbuję zasnąć."),
    X("I'm whittling.", "Strugam w drewnie."),
    X("I'm learning to make jerky.", "Uczę się robić suszone mięso."),
]
DEFS["t_u"] = [
    X("I'm starving.", "Umieram z głodu."),
    X("I'm starting to feel faint.", "Zaczyna kręcić mi się w głowie."),
    X("I'm desperate for food.", "Rozpaczliwie szukam jedzenia."),
    X("I'm gnawing on rat bones.", "Ogryzam szczurze kości."),
    X("I have terrible hunger pains.", "Mam straszne bóle z głodu."),
    X("I can barely walk.", "Ledwo chodzę."),
    X("I'm trying not to think about food.", "Staram się nie myśleć o jedzeniu."),
    X("I'm too weak to work today.", "Jestem zbyt słab{A?y|a}, żeby dziś pracować."),
    X("I'm eyeing my boots. Not yet.", "Patrzę na własne buty. Jeszcze nie."),
    X("I can hear my stomach in the quiet. It has a lot to say.", "W ciszy słyszę własny żołądek. Ma dużo do powiedzenia."),
    X("I've taken in another notch on my belt.", "Zrobi{A?łem|łam} kolejną dziurkę w pasku."),
]
DEFS["t_s"] = [
    X("I'm sick.", "Jestem chor{A?y|a}."),
    X("I've got the shakes.", "Mam dreszcze."),
    X("I stayed in bed far too long this morning.", "Dziś rano zbyt długo leża{A?łem|łam} w łóżku."),
    X("I've been coughing a lot lately.", "Ostatnio dużo kaszlę."),
    X("I need antibiotics, right away.", "Potrzebuję antybiotyków, natychmiast."),
    X("I can't stop coughing.", "Nie mogę przestać kasłać."),
    X("I haven't slept in days.", "Nie spa{A?łem|łam} od kilku dni."),
    X("I have an intense fever.", "Mam wysoką gorączkę."),
    X("I'm shivering and feverish.", "Drżę z gorączki."),
    X("I'm coughing up blood. I'm not going to think about that.", "Odkrztuszam krew. Nie będę o tym myśleć."),
    X("I can't keep anything down.", "Nic nie mogę zatrzymać w żołądku."),
    X("I'm talking to the ceiling to stay awake.", "Rozmawiam z sufitem, żeby nie zasnąć."),
    X("I'm showing early signs of scurvy.", "Mam pierwsze objawy szkorbutu."),
]

# ------------------------------------------------------------------ two survivors: narrator {A} ("I"), the other one {B}; "we" is fine, crowds are not
DUO = {}
DUO["hunger"] = [
    X("{B} and I split the last of the food in half. {B_He} insisted on the smaller half. I let it go, once.",
      "{B} i ja podzieli{AB?liśmy|łyśmy} resztki jedzenia na pół. {B?On|Ona} uparł{B?|a} się na mniejszą połowę. Odpuści{A?łem|łam} to, ten jeden raz."),
    X("{B} and I have one pot between us. We take turns pretending we're not hungry.",
      "{B} i ja mamy jeden garnek na dwoje. Na zmianę udajemy, że nie jesteśmy głod{AB?ni|ne}."),
    X("{B} says hunger is just a rumour your body believes. I'm not convinced. We're both on the floor.",
      "{B} twierdzi, że głód to tylko plotka, w którą wierzy ciało. Nie jestem {A?przekonany|przekonana}. {AB?Oboje|Obie} leżymy na podłodze."),
]
DUO["starving"] = [
    X("{B} and I haven't eaten in two days. We stopped talking about food yesterday. It stopped helping.",
      "{B} i ja od dwóch dni nic nie {AB?jedliśmy|jadłyśmy}. Wczoraj przesta{AB?liśmy|łyśmy} mówić o jedzeniu. Już nie pomagało."),
    X("{B} and I have maybe one meal left between us. We haven't decided who eats it.",
      "{B} i ja mamy może jeden posiłek na oboje. Jeszcze nie ustali{AB?liśmy|łyśmy}, kto go zje."),
]
DUO["sick"] = [
    X("{B} coughed all night. I lay awake counting. There are only the two of us, so I count.",
      "{B} kaszla{B?ł|ła} całą noc. Leża{A?łem|łam} bezsennie i liczy{A?łem|łam}. Jest nas tylko dwoje, więc liczę."),
    X("I've got {ill_a}, and {B} is doing everything now. {B_He} says it's fine. It's not. We both know it.",
      "Mam {ill_acc}, a {B} robi teraz wszystko sam{B?|a}. {B?On|Ona} mówi, że to nic. To nieprawda. {AB?Oboje|Obie} to wiemy."),
]
DUO["grief"] = [
    X("{D} is gone. {B} and I keep leaving a gap at the table where {D_he} sat. We're not ready to close it.",
      "{D} już nie ma. {B} i ja wciąż zostawiamy puste miejsce przy stole, gdzie {D?siadał|siadała}. Nie jesteśmy got{AB?owi|owe}, żeby je zasłonić."),
    X("We buried {D} together, {B} and I. We said very little. It was enough.",
      "{D}. Pochowa{AB?liśmy|łyśmy} {D?go|ją} razem, {B} i ja. Mało {AB?mówiliśmy|mówiłyśmy}. To wystarczyło."),
]
DUO["hope"] = [
    X("We fixed the roof today, {B} and I. Two pairs of hands, one decent roof.",
      "Dziś naprawi{AB?liśmy|łyśmy} dach, {B} i ja. Dwie pary rąk, jeden porządny dach."),
    X("{B} laughed today. Properly. I'd forgotten what that sounded like. I think I laughed too.",
      "{B} się dziś {B?roześmiał|roześmiała}. Naprawdę. Zapomnia{A?łem|łam}, jak to brzmi. Chyba też się {A?roześmiałem|roześmiałam}."),
]
DUO["calm"] = [
    X("A quiet evening. {B} and I sat on the step and watched the light go. Not much to say, and that was fine.",
      "Spokojny wieczór. {B} i ja {AB?siedzieliśmy|siedziałyśmy} na stopniu i {AB?patrzyliśmy|patrzyłyśmy}, jak gaśnie światło. Niewiele do powiedzenia, i dobrze."),
    X("{B} snores. I never noticed when there were more of us. Now it's the whole soundtrack of the night.",
      "{B} chrapie. Nie zauważa{A?łem|łam} tego, gdy było nas więcej. Teraz to cała ścieżka dźwiękowa nocy."),
]
DUO["despair"] = [
    X("{B} and I haven't said a full sentence to each other in a day. We aren't angry. We're just empty.",
      "{B} i ja od doby nie powiedzieli{AB?śmy|śmy} do siebie pełnego zdania. Nie jesteśmy {AB?źli|złe}. Jesteśmy po prostu {AB?puści|puste}."),
]
DUO["plenty"] = [
    X("A full pot for two. {B} and I ate in silence, and it was the best silence in weeks.",
      "Pełny garnek na dwoje. {B} i ja {AB?jedliśmy|jadłyśmy} w milczeniu i była to najlepsza cisza od tygodni."),
]


# ------------------------------------------------------------------ plumbing
def _pool_name(key):
    return ("t:solo_" + key[2:]) if key.startswith("t_") else "solo:" + key


ROWS = []                      # (pool, scope, english, polish) for the language registry
SOLO = {}                      # key -> [(scope, english)]
DUO_EN = {}                    # kind -> [(scope, english)]
TPL_POOL = {}                  # english template -> its registry pool name
for _key, _rows in DEFS.items():
    for _scope, _en, _pl in _rows:
        ROWS.append((_pool_name(_key), _scope, _en, _pl))
        TPL_POOL[_en] = _pool_name(_key)
    SOLO[_key] = [(sc, en) for sc, en, _ in _rows]
for _key, _rows in DUO.items():
    for _scope, _en, _pl in _rows:
        ROWS.append(("duo:" + _key, _scope, _en, _pl))
        TPL_POOL[_en] = "duo:" + _key
    DUO_EN[_key] = [(sc, en) for sc, en, _ in _rows]
assert len(TPL_POOL) == len(ROWS), "duplicate English template in clan_story_solo"

CAUSE_GROUP = {"illness": "illness", "bite": "illness", "bite_kin": "illness", "turned": "illness", "starved": "starved", "attack": "attack", "lost": "lost", "walkout": "lost"}
TICKER_KEY = {"s": "t_s", "u": "t_u"}


def solo_pool(kind, cause=None):
    """The one-survivor pool of a message kind (a list of (scope, template)), or None when the kind has no solo voice (it is not written)."""
    if kind == "grief":
        return SOLO["grief"] + SOLO.get("grief:" + CAUSE_GROUP.get(cause, ""), [])
    if kind == "death_bite_kin":
        kind = "death_bite"
    return SOLO.get(kind)


def solo_ticker(state):
    return SOLO[TICKER_KEY.get(state, "t_h")]


def voice_of_lid(lid):
    """"solo" / "duo" / "group" from a stored template id ("<pool>/<crc>"); no id (an old row) = group."""
    pool = (lid or "").split("/", 1)[0]
    if pool.startswith("solo:") or pool.startswith("t:solo_"):
        return "solo"
    if pool.startswith("duo:"):
        return "duo"
    return "group"
