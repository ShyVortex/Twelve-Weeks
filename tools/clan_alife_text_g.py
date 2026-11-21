"""A-Life text pools, part G (re/clan-events-1117.md): small camp incidents that go with the clan event art - damp in the stores, strangers at the
wall, a horde passing in the night, a night in the sick tent.  Row format: see clan_alife_text_a.py.
Text only, and written so that no number can be read out of it: nothing that counts is lost, nobody is hurt, nobody gets in.  A and B are two
healthy grown people in camp; the sick are never named (inc_sick is only drawn on a day the clan really has someone sick)."""

POOLS = {}

# ---- the stores: something has turned, caught in time
POOLS["inc_spoil"] = [
    ("W", "*", "{A} finds damp in the store room: two tins blown, the labels gone soft. {B} moves the rest to the dry shelf and says nothing was lost that matters.",
     "{A} znajduje wilgoć w magazynie: dwie puszki wzdęte, etykiety rozmiękłe. {B} przenosi resztę na suchą półkę i mówi, że nie stracono nic ważnego."),
    ("W", "*", "{A} opens a tin for the pot and the smell clears the kitchen. {B} checks the whole crate by lamp light; the others are sound.",
     "{A} otwiera puszkę do garnka i zapach wygania wszystkich z kuchni. {B} sprawdza całą skrzynię przy lampie; reszta jest dobra."),
    ("S", "*", "{A} finds mould in a basket of the stores and carries it out past the wall. {B} hangs the rest higher, where the smoke can reach it.",
     "{A} znajduje pleśń w koszu z zapasami i wynosi go za palisadę. {B} wiesza resztę wyżej, tam gdzie sięga dym."),
    ("S", "*", "A jar in the store house has turned. {A} buries it; {B} says a prayer over the others and counts them twice.",
     "Jeden słój w spichrzu się zepsuł. {A} go zakopuje; {B} odmawia modlitwę nad pozostałymi i liczy je dwa razy."),
]

# ---- strangers at the wall: signs only, nobody gets in
POOLS["inc_tres"] = [
    ("W", "*", "{A} finds a cut in the fence wire at first light, and boot prints that are not ours. {B} walks the line twice and has it mended before breakfast.",
     "{A} znajduje o świcie przecięty drut w ogrodzeniu i ślady butów, które nie są nasze. {B} obchodzi linię dwa razy i każe ją naprawić przed śniadaniem."),
    ("W", "*", "Someone was at the wall in the night: {A} hears a stone turn and then nothing. {B} sits up with the rifle until morning; nobody comes.",
     "Ktoś był w nocy pod murem: {A} słyszy potrącony kamień, a potem nic. {B} siedzi z karabinem do rana; nikt nie przychodzi."),
    ("S", "*", "{A} finds strange tracks under the palisade, three people, light on their feet. {B} follows them to the water, where they end.",
     "{A} znajduje pod palisadą obce ślady, trzy osoby, lekki krok. {B} idzie za nimi do wody, gdzie się urywają."),
    ("S", "*", "A whistle answers the watch that is not one of ours. {A} whistles again and gets silence. {B} wakes the others, quietly, for nothing.",
     "Warcie odpowiada gwizd, który nie jest nasz. {A} gwiżdże jeszcze raz i dostaje ciszę. {B} budzi pozostałych, po cichu, na próżno."),
]

# ---- a horde in the night: it goes by
POOLS["inc_horde"] = [
    ("*", "*", "A horde goes by in the dark, a long way off, the sound of it like weather. {A} puts the lamps out. {B} counts the minutes until it is gone.",
     "W ciemności, daleko, przechodzi horda; brzmi jak nadciągająca pogoda. {A} gasi lampy. {B} liczy minuty, aż ucichnie."),
    ("*", "*", "{A} wakes the camp without a word: the infected are on the road, dozens of them, heading somewhere else. {B} holds the gate shut with both hands until the road is empty.",
     "{A} budzi obóz bez słowa: drogą idą zarażeni, dziesiątki, gdzieś indziej. {B} trzyma bramę obiema rękami, aż droga opustoszeje."),
]

# ---- the sick tent (only on a day somebody really is sick; the sick are not named)
POOLS["inc_sick"] = [
    ("*", "*", "{A} sits up in the sick tent through the night with a bowl and a cloth. {B} takes over at dawn and orders sleep.",
     "{A} czuwa całą noc w namiocie chorych z miską i szmatką. {B} przejmuje czuwanie o świcie i każe iść spać."),
    ("*", "*", "{A} boils every cloth from the sick tent and hangs them in the smoke. {B} carries water until the barrel is full.",
     "{A} wygotowuje wszystkie szmaty z namiotu chorych i wiesza je w dymie. {B} nosi wodę, aż beczka jest pełna."),
]
