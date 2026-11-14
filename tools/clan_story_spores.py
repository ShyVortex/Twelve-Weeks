"""Clan feed lines about the spores (TLOU canon): whoever breathes the spores without a mask is infected, and there is no cure and no recovery.
The end is always the same: the person turns, or the clan chooses (a mercy, an exile, a walk into the dark, a last request).  A bite is the same.

Every row carries both languages side by side (scope, English, Polish) so the pair cannot drift: ROWS = [(pool, scope, english, polish)] feeds the language registry
(clan_story_pl._build) and LINES = {pool: [(scope, english)]} feeds the English pools (clan_story.LINES).  The arc that tells the whole story in cards is "spore" in
tools/clan_arcs.py (text: tools/clan_arcs_text2.py).

Pools:  death_turned   the day a spore-sick member is gone (turned / asked for mercy / walked off into the dark); {A} the dead, {B} the one who had to
        grief_turned   the grief of {A} after {D} (who is gone to the spores)
        spore_worse    a spore-sick {A} is worse (replaces the generic "worse": no cure, no filters, no talk of recovery)
        spore_hold     the camp tries for {A} and there is nothing to find (replaces the generic "medicine")
"""
POOLS = {}

POOLS["death_turned"] = [
    ("*", "{A} told {B} plainly, at the fire, that it was the spores, and asked for one more night. {B} gave it. Nobody slept, and nobody called it weakness.",
     "{A} powiedział{A?|a} {B} wprost, przy ogniu, że to zarodniki, i poprosił{A?|a} o jeszcze jedną noc. {B} {B?dał|dała} ją. Nikt nie spał i nikt nie nazwał tego słabością."),
    ("*", "The cough was only the start. By the third day {A} stopped answering to {A_his} name, and {B} did what {A} had asked while {A_he} could still ask.",
     "Kaszel był dopiero początkiem. Trzeciego dnia {A} przestał{A?|a} reagować na własne imię, a {B} zrobił{B?|a} to, o co {A} prosił{A?|a}, dopóki jeszcze {A?mógł|mogła}."),
    ("*", "There is no medicine for what {A} breathed in, and we all know it. {A} turned at dawn. {B} was already waiting at the door with the rifle and a blanket.",
     "Na to, co {A} wdychał{A?|a}, nie ma lekarstwa i wszyscy o tym wiemy. {A} przemieni{A?ł|ła} się o świcie. {B} już czekał{B?|a} przy drzwiach z karabinem i kocem."),
    ("*", "{A} asked us not to watch. We didn't. We heard the single shot, and then {B} came back with {A}'s coat and hung it on the hook.",
     "{A} poprosił{A?|a}, żebyśmy nie patrzyli. Nie patrzyliśmy. Usłyszeliśmy jeden strzał, a potem {B} wrócił{B?|a} z płaszczem {A} i powiesił{B?|a} go na haku."),
    ("*", "{A} walked out at dusk, quietly, past the last light, before it could take {A_him} in front of us. Nobody followed. That was {A}'s last request, and we kept it.",
     "{A} {A?wyszedł|wyszła} o zmierzchu, cicho, poza ostatnie światło, zanim to zdążyło {A?go|ją} zabrać na naszych oczach. Nikt nie poszedł za {A?nim|nią}. To była ostatnia prośba {A}, i dotrzymaliśmy jej."),
    ("*", "The spores finished what they started. {A} was gone by morning, and {B} sat with what was left until the sun was fully up.",
     "Zarodniki dokończyły to, co zaczęły. Rano {A} już z nami nie by{A?ł|ła}, a {B} siedział{B?|a} przy tym, co zostało, aż słońce wzeszło na dobre."),
    ("W", "Spores don't forgive and there's no cure, so {A} asked for it quick. {B} did it out past the {place}. Fuck. Fuck this world.",
     "Zarodniki nie wybaczają i nie ma na nie lekarstwa, więc {A} poprosił{A?|a}, żeby było szybko. {B} zrobił{B?|a} to za {place_ins}. Kurwa. Pierdolę ten świat."),
    ("W", "{A} left on {A_his} own two feet, mask in hand, with a day's walk before the fungus would take {A_him}. We let {A_him} go. That's the whole story.",
     "{A} {A?odszedł|odeszła} na własnych nogach, z maską w ręku, mając przed sobą dzień drogi, zanim grzyb {A?go|ją} zabierze. Pozwoliliśmy na to. To cała historia."),
    ("W", "The medic wouldn't say it, so {A} said it: 'It's the spores. Don't let me get up again.' {B} didn't. Nobody at the {place} will forget how steady {B_his} hand was.",
     "Medyk nie chciał tego powiedzieć, więc powiedział{A?|a} to {A}: „To zarodniki. Nie pozwólcie mi wstać.” {B} nie pozwolił{B?|a}. Nikt {place_at} nie zapomni, jak pewną rękę miał{B?|a} {B}."),
    ("S", "{A} walked down to the water at dusk, and the Elders let {A_him} go. The spores take everyone who breathes them. {A} chose where.",
     "{A} {A?zszedł|zeszła} o zmierzchu nad wodę, a Starsi pozwolili na to. Zarodniki zabierają każdego, kto je wdycha. {A} wybrał{A?|a} miejsce."),
    ("S", "{B} sat by {A} through the long night. At dawn {A} asked to be carried to the shore, and {B} carried {A_him}, and came back alone.",
     "{B} przesiedział{B?|a} przy {A?nim|niej} całą długą noc. O świcie {A} poprosił{A?|a}, żeby zanieść {A?go|ją} na brzeg, i {B} zaniósł{B?|a} {A?go|ją}, i wrócił{B?|a} {B?sam|sama}."),
    ("S", "{A} sang in the long house until the voice stopped being a voice, and the Elders did what the Prophet's way asks of them. We stood outside until it was quiet.",
     "{A} śpiewał{A?|a} w długim domu, aż głos przestał być głosem, a Starsi zrobili to, czego wymaga droga Prorokini. Staliśmy na zewnątrz, aż zrobiło się cicho."),
]

POOLS["grief_turned"] = [
    ("*", "{A} keeps glancing at the door {D} went through. {A} knows what happened. Knowing doesn't help.",
     "{A} wciąż zerka na drzwi, którymi {D?wyszedł|wyszła} {D}. {A} wie, co się stało. Wiedza nie pomaga."),
    ("*", "{A} can't stand the smell of a cellar any more, or the word spores. One day {D} was breathing fine, and then {D_he} wasn't.",
     "{A} nie znosi już zapachu piwnicy ani słowa „zarodniki”. Jednego dnia {D} oddychał{D?|a} normalnie, a potem już nie."),
    ("*", "{A} hangs {D}'s mask on its hook every evening, though there is no one left to wear it. It was never the mask's fault. {A} knows that, and does it anyway.",
     "{A} co wieczór wiesza maskę {D} na haku, choć nie ma już komu jej nosić. To nigdy nie była wina maski. {A} o tym wie i robi to mimo wszystko."),
    ("*", "{A} asked the medic again whether anything could have been done. The medic gave the same answer, gently. {A} nodded and went on asking.",
     "{A} znów zapytał{A?|a} medyka, czy dało się coś zrobić. Medyk odpowiedział tak samo, łagodnie. {A} {A?skinął|skinęła} głową i dalej pytał{A?|a}."),
    ("*", "{A} sits up late with {D}'s coat across {A_his} knees. There was nothing left to bury. The coat will have to do.",
     "{A} siedzi do późna z płaszczem {D} na kolanach. Nie zostało nic do pochowania. Płaszcz będzie musiał wystarczyć."),
    ("*", "The camp has agreed on a story about {D}: good with a rope, bad at singing, a quiet end. {A} lets them tell it. {A} is the only one who also remembers the cough.",
     "Obóz uzgodnił opowieść o {D}: dobre ręce do liny, zły śpiew, cichy koniec. {A} pozwala im ją opowiadać. Tylko {A} pamięta też kaszel."),
    ("W", "{A} won't go near the {place} since {D} turned. Says the air tastes different there. Maybe it does.",
     "{A} nie chce być {place_at} od czasu, gdy {D} się przemieni{D?ł|ła}. Mówi, że powietrze ma tam inny smak. Może ma."),
    ("W", "Nobody mentions {D}'s cough. {A} washes {D}'s cup every night anyway, and hangs it up, and says nothing. Fucking spores.",
     "Nikt nie wspomina o kaszlu {D}. {A} i tak co wieczór myje kubek {D}, wiesza go i nic nie mówi. Pieprzone zarodniki."),
    ("S", "{A} lights a candle for {D} and lets it burn past dawn. The Elders say Her Light does not turn away from the sick. {A} asks why it could not have saved {D_him}.",
     "{A} zapala świecę za {D} i pozwala jej płonąć po świt. Starsi mówią, że Jej Światło nie odwraca się od chorych. {A} pyta, czemu nie mogło uratować {D?go|jej}."),
    ("S", "The little ones ask {A} where {D} went. {A} says to the Light, then sits down in the rain with the mask in {A_his} lap.",
     "Maluchy pytają {A}, dokąd {D?poszedł|poszła} {D}. {A} odpowiada, że do Światła, po czym siada w deszczu z maską na kolanach."),
]

POOLS["spore_worse"] = [
    ("*", "{A} is worse. Grey dust on the pillow, red eyes, a cough that doesn't stop. We all know there is no coming back from this.",
     "{A} czuje się gorzej. Szary pył na poduszce, czerwone oczy, kaszel, który nie ustaje. Wszyscy wiemy, że z tego nie ma powrotu."),
    ("*", "{B} keeps the mask on and sits close anyway. {A} has stopped asking whether it will pass.",
     "{B} nie zdejmuje maski i mimo to siedzi blisko. {A} przestał{A?|a} pytać, czy to minie."),
    ("*", "{A} has started to lose small things: a name, the way to the well. {B} writes them down for {A_him}. We all pretend we don't know why.",
     "{A} {A?zaczął|zaczęła} gubić drobne rzeczy: imię, drogę do studni. {B} zapisuje je dla {A?niego|niej}. Wszyscy udajemy, że nie wiemy dlaczego."),
    ("*", "There was never any medicine for this. {A} knows it. {A} asked {B} for a promise, and {B} gave it. Neither of them has said what it was.",
     "Na to nigdy nie było lekarstwa. {A} o tym wie. {A} poprosił{A?|a} {B} o obietnicę i {B} jej udzielił{B?|a}. Żadne z nich nie powiedziało, co to było."),
    ("W", "{A} loses the thread mid-sentence now. Spores. No filter on earth fixes it after the fact. The medic won't look anyone in the eye.",
     "{A} gubi wątek w pół zdania. Zarodniki. Żaden filtr na świecie nie pomoże po fakcie. Medyk nie patrzy nikomu w oczy."),
    ("S", "{A} is quiet and burning with fever. The Elders say we will know when the time has come. {B} keeps the vigil, and keeps {B_his} face still.",
     "{A} jest cich{A?y|a} i płonie w gorączce. Starsi mówią, że poznamy, kiedy przyjdzie czas. {B} czuwa i trzyma twarz nieruchomo."),
]

POOLS["spore_hold"] = [
    ("*", "We turned the camp upside down looking for something for {A}'s lungs. There isn't anything. We stopped looking and just sat with {A_him}.",
     "Przewróciliśmy obóz do góry nogami w poszukiwaniu czegoś na płuca {A}. Niczego nie ma. Przestaliśmy szukać i po prostu usiedliśmy przy {A?nim|niej}."),
    ("*", "{B} boiled every herb in the kit for {A}. {A} drank it to be kind. Everyone knows what the spores are.",
     "{B} ugotował{B?|a} dla {A} wszystkie zioła z apteczki. {A} wypił{A?|a} to z uprzejmości. Wszyscy wiedzą, czym są zarodniki."),
    ("*", "Nobody asks for medicine for {A} anymore. We ask for time instead, and no one can sell us that either.",
     "Nikt już nie prosi o lekarstwo dla {A}. Prosimy o czas, a tego też nikt nie sprzeda."),
    ("W", "Medic says it flat: spores are a one-way road. We keep {A} comfortable and keep our distance, and I hate us both for it.",
     "Medyk mówi to wprost: zarodniki to droga w jedną stronę. Dbamy, żeby {A?mu|jej} było wygodnie, i trzymamy dystans, i nienawidzę nas za to."),
    ("S", "The healers cannot help {A}. The sea washes away much, but not this. We bring water and song and nothing else.",
     "Uzdrowiciele nie mogą pomóc {A?jemu|jej}. Morze zmywa wiele, ale nie to. Przynosimy wodę i pieśń, i nic więcej."),
]

# extra onset lines for the illness "spores" (appended to the onset pools of clan_story_lines_dark.py / clan_story_pl_dark.py by index: English, Polish)
ONSET_EN = [
    ("*", "{A} didn't notice the mask had cracked until the cellar was already full of spores. The cough started that evening. {B} won't let anyone else into the room."),
    ("W", "{A}'s mask seal failed in the old subway. One breath was all it took. {A} knows what that means. So do we."),
    ("S", "{A} drew a deep breath in the old cellar before anyone could stop {A_him}. {A} came back singing, and by night the cough began. We have not told the little ones."),
]
ONSET_PL = [
    "{A} nie zauważył{A?|a}, że maska pękła, dopóki piwnica nie wypełniła się zarodnikami. Kaszel zaczął się wieczorem. {B} nie wpuszcza nikogo więcej do pokoju.",
    "Uszczelka w masce {A} puściła w starym metrze. Jeden oddech wystarczył. {A} wie, co to znaczy. My też.",
    "{A} {A?wziął|wzięła} głęboki oddech w starej piwnicy, zanim ktokolwiek zdążył {A?go|ją} powstrzymać. Wrócił{A?|a} śpiewając, a w nocy zaczął się kaszel. Nie powiedzieliśmy maluchom.",
]

LINES = {k: [(sc, en) for sc, en, _pl in rows] for k, rows in POOLS.items()}
ROWS = [(k, sc, en, pl) for k, rows in POOLS.items() for sc, en, pl in rows]
