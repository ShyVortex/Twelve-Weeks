"""Data of the clan loot model (tools/clan_loot.py): the item table.  English + Polish, no logic.  Places, conditions and hooks: clan_loot_data2.py.

ITEMS: one row per line, '|' separated:
  key | cat | tier | rarity | qty min-max | value per piece | kinds | icon | gender | EN one | EN many | PL nominative | PL accusative | PL 2-4 | PL 5+
  cat    food water med ammo mat tool cloth fuel trink book seed anim part     (supply group: see GROUP)
  tier   0 scraps, 1 poor, 2 normal, 3 good, 4 luxurious      rarity 0 common, 1 uncommon, 2 rare
  kinds  place kinds the item belongs to (affinity with the map's kinds, clan_loot_data2.MAP_KINDS): ph pharmacy, ho hospital, mi military, ca Seraphite camp, ra rail,
         ma marine / fishing, hs house, sc school, sh shop, hw hardware, ht hotel / lodge, wi wild, of office, fa farm / garden
  icon   the icon id the launcher SHOULD have (clan-icons.js lacks many: clan_loot.icon_for falls back to a category icon)
  gender PL m / f / n (inanimate things or animals in the feminine only, so the accusative of a masculine equals its nominative)
  EN one is the noun group without article ('can of pineapple'); '-' in the plural columns = the item is never found in numbers.
  PL phrases always start with the head noun, so a condition adjective can be put in front ('zardzewiałą puszkę ananasa').
"""
ITEMS = r"""
pine|food|2|0|1-4|1|hs,sh|food|f|can of pineapple|cans of pineapple|puszka ananasa|puszkę ananasa|puszki ananasa|puszek ananasa
beans|food|2|0|1-4|1|hs,sh,mi|food|f|can of beans|cans of beans|puszka fasoli|puszkę fasoli|puszki fasoli|puszek fasoli
peaches|food|3|1|1-3|1|hs,sh|food|f|can of peaches|cans of peaches|puszka brzoskwiń|puszkę brzoskwiń|puszki brzoskwiń|puszek brzoskwiń
sardines|food|2|0|1-4|1|ma,hs|food|f|tin of sardines|tins of sardines|puszka sardynek|puszkę sardynek|puszki sardynek|puszek sardynek
tuna|food|2|0|1-3|1|ma,hs,sh|food|f|can of tuna|cans of tuna|puszka tuńczyka|puszkę tuńczyka|puszki tuńczyka|puszek tuńczyka
tomsoup|food|2|0|1-3|1|hs,sh|food|f|can of tomato soup|cans of tomato soup|puszka zupy pomidorowej|puszkę zupy pomidorowej|puszki zupy pomidorowej|puszek zupy pomidorowej
corn|food|1|0|1-4|1|hs,sh,fa|food|f|can of corn|cans of corn|puszka kukurydzy|puszkę kukurydzy|puszki kukurydzy|puszek kukurydzy
nolabel|food|0|0|1-3|1|*|food|f|can with no label|cans with no label|puszka bez etykiety|puszkę bez etykiety|puszki bez etykiety|puszek bez etykiety
dogfood|food|0|0|1-3|1|hs,sh,fa|food|f|can of dog food|cans of dog food|puszka karmy dla psów|puszkę karmy dla psów|puszki karmy dla psów|puszek karmy dla psów
crackers|food|1|0|1-3|1|*|food|f|sleeve of crackers|sleeves of crackers|paczka krakersów|paczkę krakersów|paczki krakersów|paczek krakersów
crust|food|0|0|1-2|1|hs,ht|food|f|crust of bread|crusts of bread|skórka chleba|skórkę chleba|skórki chleba|skórek chleba
hardtack|food|1|0|1-3|1|mi,ma|food|f|pack of hardtack|packs of hardtack|paczka sucharów|paczkę sucharów|paczki sucharów|paczek sucharów
noodles|food|1|0|1-4|1|hs,sh,ht|food|f|pack of instant noodles|packs of instant noodles|paczka makaronu błyskawicznego|paczkę makaronu błyskawicznego|paczki makaronu błyskawicznego|paczek makaronu błyskawicznego
rice|food|2|0|1-2|3|hs,sh,ca|grain|m|bag of rice|bags of rice|worek ryżu|worek ryżu|worki ryżu|worków ryżu
flour|food|2|0|1-2|3|hs,ca,fa|grain|m|sack of flour|sacks of flour|worek mąki|worek mąki|worki mąki|worków mąki
salt|food|2|1|1-1|2|hs,ca,ma|salt|m|bag of salt|-|woreczek soli|woreczek soli|-|-
sugar|food|3|1|1-1|2|hs,sh,ht|sweets|f|bag of sugar|-|torebka cukru|torebkę cukru|-|-
oats|food|2|0|1-2|2|hs,ca|grain|f|tin of oats|tins of oats|puszka płatków owsianych|puszkę płatków owsianych|puszki płatków owsianych|puszek płatków owsianych
pasta|food|2|0|1-3|2|hs,sh|grain|f|box of pasta|boxes of pasta|paczka makaronu|paczkę makaronu|paczki makaronu|paczek makaronu
cereal|food|1|0|1-2|1|hs,sc,sh|grain|n|box of cereal|boxes of cereal|pudełko płatków śniadaniowych|pudełko płatków śniadaniowych|pudełka płatków śniadaniowych|pudełek płatków śniadaniowych
granola|food|2|0|2-6|1|hs,wi,sh|food|m|granola bar|granola bars|baton zbożowy|baton zbożowy|batony zbożowe|batonów zbożowych
jerky|food|3|1|1-2|2|wi,ca,hs|food|m|bag of jerky|bags of jerky|woreczek suszonego mięsa|woreczek suszonego mięsa|woreczki suszonego mięsa|woreczków suszonego mięsa
honey|food|3|1|1-2|2|ca,fa,hs|sweets|m|jar of honey|jars of honey|słoik miodu|słoik miodu|słoiki miodu|słoików miodu
jam|food|3|0|1-3|1|hs,ca,fa|sweets|m|jar of jam|jars of jam|słoik dżemu|słoik dżemu|słoiki dżemu|słoików dżemu
pickles|food|2|0|1-3|1|hs,ca,fa|food|m|jar of pickles|jars of pickles|słoik ogórków|słoik ogórków|słoiki ogórków|słoików ogórków
cookies|food|3|0|1-3|1|hs,sh,ht|sweets|n|packet of cookies|packets of cookies|opakowanie ciastek|opakowanie ciastek|opakowania ciastek|opakowań ciastek
peanut|food|3|1|1-2|2|hs,sh|food|m|jar of peanut butter|jars of peanut butter|słoik masła orzechowego|słoik masła orzechowego|słoiki masła orzechowego|słoików masła orzechowego
ham|food|3|1|1-2|2|hs,sh,ht|food|f|tin of ham|tins of ham|puszka szynki|puszkę szynki|puszki szynki|puszek szynki
oil|food|2|0|1-1|2|hs,sh,ht|food|f|bottle of cooking oil|-|butelka oleju|butelkę oleju|-|-
cocoa|food|3|1|1-1|2|hs,ht,sh|sweets|f|tin of cocoa|-|puszka kakao|puszkę kakao|-|-
tea|food|3|1|1-2|2|hs,ht,ca|coffee|n|box of tea|boxes of tea|pudełko herbaty|pudełko herbaty|pudełka herbaty|pudełek herbaty
chocolate|food|4|1|1-3|2|hs,ht,sh|sweets|f|bar of chocolate|bars of chocolate|tabliczka czekolady|tabliczkę czekolady|tabliczki czekolady|tabliczek czekolady
coffee|food|4|2|1-1|3|hs,ht,sh|coffee|f|tin of real coffee|-|puszka prawdziwej kawy|puszkę prawdziwej kawy|-|-
fruit|food|4|1|2-6|1|fa,ca,wi|fruit|n|piece of fresh fruit|pieces of fresh fruit|owoc|owoc|owoce|owoców
apples|food|3|0|2-8|1|fa,ca,wi,hs|fruit|n|apple|apples|jabłko|jabłko|jabłka|jabłek
eggs|food|3|1|2-10|1|fa,ca,hs|eggs|n|chicken egg|chicken eggs|jajko|jajko|jajka|jajek
smokedfish|food|2|0|1-3|2|ma,ca,wi|fish|f|smoked fish|smoked fish|ryba wędzona|rybę wędzoną|ryby wędzone|ryb wędzonych
trout|food|2|0|1-2|2|ma,wi,ca|fish|f|string of trout|strings of trout|wiązka pstrągów|wiązkę pstrągów|wiązki pstrągów|wiązek pstrągów
mushrooms|food|1|0|1-2|1|wi,ca|food|m|basket of mushrooms|baskets of mushrooms|koszyk grzybów|koszyk grzybów|koszyki grzybów|koszyków grzybów
berries|food|1|0|1-2|1|wi,ca,fa|fruit|f|handful of berries|handfuls of berries|garść jagód|garść jagód|garście jagód|garści jagód
venison|food|3|1|1-1|4|wi,ca,ht|food|m|haunch of venison|-|udziec sarniny|udziec sarniny|-|-
whiskey|food|4|2|1-1|1|ht,hs,sh,of|alcohol|f|bottle of whiskey|-|butelka whisky|butelkę whisky|-|-
wine|food|3|1|1-2|1|ht,hs,sh|alcohol|f|bottle of wine|bottles of wine|butelka wina|butelkę wina|butelki wina|butelek wina
rainwater|water|0|0|1-2|2|*|water|n|bucket of rainwater|buckets of rainwater|wiadro deszczówki|wiadro deszczówki|wiadra deszczówki|wiader deszczówki
snowpot|water|0|0|1-1|2|wi,hs|water|m|pot of melted snow|-|garnek stopionego śniegu|garnek stopionego śniegu|-|-
cloudy|water|0|0|1-2|1|*|water|f|bottle of cloudy water|bottles of cloudy water|butelka mętnej wody|butelkę mętnej wody|butelki mętnej wody|butelek mętnej wody
well|water|1|0|1-2|2|hs,fa,ca|water|m|jar of well water|jars of well water|słoik wody ze studni|słoik wody ze studni|słoiki wody ze studni|słoików wody ze studni
waterbottle|water|1|0|1-6|1|*|water|f|bottle of water|bottles of water|butelka wody|butelkę wody|butelki wody|butelek wody
boiled|water|1|0|1-2|2|hs,ca|water|m|jug of boiled water|jugs of boiled water|dzban wody przegotowanej|dzban wody przegotowanej|dzbany wody przegotowanej|dzbanów wody przegotowanej
tablets|water|2|1|1-1|4|ph,ho,mi,hw|pills|f|bottle of water purification tablets|-|buteleczka tabletek do uzdatniania wody|buteleczkę tabletek do uzdatniania wody|-|-
waterskin|water|2|0|1-1|2|wi,ca,mi|water|m|waterskin|-|bukłak na wodę|bukłak na wodę|-|-
mineral|water|2|0|1-4|1|sh,ht,hs|water|f|bottle of mineral water|bottles of mineral water|butelka wody mineralnej|butelkę wody mineralnej|butelki wody mineralnej|butelek wody mineralnej
cistern|water|2|0|1-2|2|ca|water|m|pitcher of cistern water|pitchers of cistern water|dzban wody z cysterny|dzban wody z cysterny|dzbany wody z cysterny|dzbanów wody z cysterny
canteen|water|2|0|1-2|2|mi,wi,ca|water|f|canteen of clean water|canteens of clean water|manierka czystej wody|manierkę czystej wody|manierki czystej wody|manierek czystej wody
filter|water|3|1|1-2|4|mi,ra,hw,of|filter|m|water filter|water filters|filtr do wody|filtr do wody|filtry do wody|filtrów do wody
juice|water|3|0|1-3|2|hs,sh,sc|fruit|m|carton of juice|cartons of juice|karton soku|karton soku|kartony soku|kartonów soku
soda|water|3|0|1-3|1|sh,ht,sc|sweets|f|bottle of soda|bottles of soda|butelka napoju gazowanego|butelkę napoju gazowanego|butelki napoju gazowanego|butelek napoju gazowanego
sparkling|water|4|1|1-2|2|sh,ht|water|f|bottle of sparkling mineral water|bottles of sparkling mineral water|butelka wody mineralnej gazowanej|butelkę wody mineralnej gazowanej|butelki wody mineralnej gazowanej|butelek wody mineralnej gazowanej
waterpack|water|4|1|1-1|10|sh,ht,mi|water|f|case of bottled spring water|-|zgrzewka wody źródlanej|zgrzewkę wody źródlanej|-|-
dressing|med|0|0|1-4|1|*|bandage|m|cloth strip for dressings|cloth strips for dressings|pasek płótna na opatrunek|pasek płótna na opatrunek|paski płótna na opatrunek|pasków płótna na opatrunek
bandage|med|1|0|1-5|1|ph,ho,hs|bandage|m|bandage|bandages|bandaż|bandaż|bandaże|bandaży
gauze|med|2|0|1-3|1|ph,ho|bandage|f|roll of gauze|rolls of gauze|rolka gazy|rolkę gazy|rolki gazy|rolek gazy
abx|med|3|1|1-2|3|ph,ho|pills|n|pack of antibiotics|packs of antibiotics|opakowanie antybiotyków|opakowanie antybiotyków|opakowania antybiotyków|opakowań antybiotyków
abxbox|med|4|2|1-1|8|ph,ho|pills|n|box of antibiotics|-|pudełko antybiotyków|pudełko antybiotyków|-|-
painkillers|med|2|0|1-2|2|ph,ho,hs|pills|n|bottle of painkillers|bottles of painkillers|opakowanie leków przeciwbólowych|opakowanie leków przeciwbólowych|opakowania leków przeciwbólowych|opakowań leków przeciwbólowych
aspirin|med|1|0|1-2|1|ph,hs,sc|pills|n|box of aspirin|boxes of aspirin|pudełko aspiryny|pudełko aspiryny|pudełka aspiryny|pudełek aspiryny
alcohol|med|1|0|1-3|1|ph,ho,hs|alcohol|f|bottle of rubbing alcohol|bottles of rubbing alcohol|butelka spirytusu|butelkę spirytusu|butelki spirytusu|butelek spirytusu
antiseptic|med|2|0|1-2|2|ph,ho,sc|medicine|f|bottle of antiseptic|bottles of antiseptic|butelka środka odkażającego|butelkę środka odkażającego|butelki środka odkażającego|butelek środka odkażającego
supplements|med|2|1|1-2|2|ph,ho,mi|pills|n|bottle of supplements|bottles of supplements|opakowanie suplementów|opakowanie suplementów|opakowania suplementów|opakowań suplementów
insulin|med|4|2|1-1|8|ph,ho|insulin|f|vial of insulin|-|fiolka insuliny|fiolkę insuliny|-|-
firstaid|med|3|0|1-1|6|ph,ho,sc,of|first-aid|f|first-aid kit|-|apteczka|apteczkę|-|-
trauma|med|4|2|1-1|10|mi,ho|first-aid|m|trauma kit|-|zestaw ratunkowy|zestaw ratunkowy|-|-
thermometer|med|2|0|1-1|2|ph,ho,hs|medicine|m|thermometer|-|termometr|termometr|-|-
eyedrops|med|2|0|1-2|1|ph,ho|medicine|f|bottle of eye drops|bottles of eye drops|buteleczka kropli do oczu|buteleczkę kropli do oczu|buteleczki kropli do oczu|buteleczek kropli do oczu
syrup|med|2|0|1-2|2|ph,hs|medicine|f|bottle of cough syrup|bottles of cough syrup|butelka syropu na kaszel|butelkę syropu na kaszel|butelki syropu na kaszel|butelek syropu na kaszel
sutures|med|3|1|1-1|4|ho,mi|medicine|m|suture kit|-|zestaw do szycia ran|zestaw do szycia ran|-|-
splint|med|2|0|1-3|1|ho,mi|medicine|f|splint|splints|szyna|szynę|szyny|szyn
yarrow|med|1|0|1-3|1|ca,wi|herb|m|bundle of dried yarrow|bundles of dried yarrow|pęczek krwawnika|pęczek krwawnika|pęczki krwawnika|pęczków krwawnika
salve|med|2|1|1-2|2|ca|medicine|m|jar of herbal salve|jars of herbal salve|słoiczek maści ziołowej|słoiczek maści ziołowej|słoiczki maści ziołowej|słoiczków maści ziołowej
r38|ammo|2|0|5-20|1|hs,mi,sh|pistolammo|m|.38 round|.38 rounds|nabój .38|nabój .38|naboje .38|naboi .38
r22|ammo|0|0|5-25|1|hs,wi,sh|pistolammo|m|.22 round|.22 rounds|nabój .22|nabój .22|naboje .22|naboi .22
box9|ammo|3|0|1-3|3|mi,hs,of|pistolammo|n|box of 9mm|boxes of 9mm|pudełko 9 mm|pudełko 9 mm|pudełka 9 mm|pudełek 9 mm
shells|ammo|2|0|2-8|1|hs,mi,wi|shotgunammo|m|shotgun shell|shotgun shells|nabój do strzelby|nabój do strzelby|naboje do strzelby|naboi do strzelby
rifleammo|ammo|3|1|1-3|3|mi|rifleammo|n|box of rifle rounds|boxes of rifle rounds|pudełko nabojów karabinowych|pudełko nabojów karabinowych|pudełka nabojów karabinowych|pudełek nabojów karabinowych
arrows|ammo|2|0|2-8|1|ca,wi,hw|arrow|f|arrow|arrows|strzała|strzałę|strzały|strzał
bolts|ammo|2|0|2-8|1|ca,wi,hw|arrow|m|crossbow bolt|crossbow bolts|bełt|bełt|bełty|bełtów
ammocrate|ammo|4|2|1-1|12|mi|rifleammo|f|ammo crate|-|skrzynka z amunicją|skrzynkę z amunicją|-|-
flares|ammo|1|0|1-3|1|mi,ma,ra|explosive|f|flare|flares|raca|racę|race|rac
scrap|mat|0|0|2-9|1|*|parts|m|piece of scrap metal|pieces of scrap metal|kawałek złomu|kawałek złomu|kawałki złomu|kawałków złomu
rags|mat|0|0|2-8|1|*|rag|f|rag|rags|szmata|szmatę|szmaty|szmat
tape|mat|1|0|1-2|1|hw,of,ra,hs|tape|f|roll of tape|rolls of tape|rolka taśmy|rolkę taśmy|rolki taśmy|rolek taśmy
blades|mat|1|0|2-6|1|hw,hs,sh|blade|n|razor blade|razor blades|ostrze|ostrze|ostrza|ostrzy
binding|mat|1|0|1-4|1|ph,ho,hs|binding|f|roll of binding|rolls of binding|rolka opaski|rolkę opaski|rolki opaski|rolek opaski
gunpowder|mat|2|1|1-2|2|mi,hw|explosive|f|tin of gunpowder|tins of gunpowder|puszka prochu|puszkę prochu|puszki prochu|puszek prochu
explosive|mat|3|1|1-1|4|mi|explosive|m|pouch of explosive|-|woreczek materiału wybuchowego|woreczek materiału wybuchowego|-|-
pipe|mat|1|0|1-3|1|hw,ra,ma|pipe|m|length of pipe|lengths of pipe|kawałek rury|kawałek rury|kawałki rury|kawałków rury
nails|mat|1|0|1-3|1|hw,hs|nails|n|box of nails|boxes of nails|pudełko gwoździ|pudełko gwoździ|pudełka gwoździ|pudełek gwoździ
nutsbolts|mat|1|0|1-2|1|hw,ra,ma|nails|m|jar of nuts and bolts|jars of nuts and bolts|słoik śrubek i nakrętek|słoik śrubek i nakrętek|słoiki śrubek i nakrętek|słoików śrubek i nakrętek
wire|mat|2|0|1-2|2|hw,ra,of|wire|f|spool of wire|spools of wire|szpula drutu|szpulę drutu|szpule drutu|szpul drutu
rope|mat|2|0|1-2|2|ma,hw,ca|rope|m|coil of rope|coils of rope|zwój liny|zwój liny|zwoje liny|zwojów liny
cloth|mat|2|0|1-1|3|ca,sh,hs|cloth|f|bolt of cloth|-|bela płótna|belę płótna|-|-
planks|mat|1|0|1-2|2|hw,hs,wi|planks|f|bundle of planks|bundles of planks|wiązka desek|wiązkę desek|wiązki desek|wiązek desek
solvent|mat|2|0|1-2|2|hw,mi|canister|f|bottle of solvent|bottles of solvent|butelka rozpuszczalnika|butelkę rozpuszczalnika|butelki rozpuszczalnika|butelek rozpuszczalnika
wrench|tool|2|0|1-1|2|hw,ra,ma|wrench|m|wrench|-|klucz francuski|klucz francuski|-|-
hammer|tool|2|0|1-1|2|hw,hs,ma|hammer|m|hammer|-|młotek|młotek|-|-
screwdrivers|tool|2|0|1-1|2|hw,of|wrench|m|set of screwdrivers|-|zestaw wkrętaków|zestaw wkrętaków|-|-
pliers|tool|2|0|1-1|2|hw,ra|wrench|f|pair of pliers|-|para szczypiec|parę szczypiec|-|-
scissors|tool|1|0|1-2|1|hs,sc,ph,ca|scissors|f|pair of scissors|pairs of scissors|para nożyczek|parę nożyczek|pary nożyczek|par nożyczek
saw|tool|2|0|1-1|2|hw,wi,hs|saw|f|saw|-|piła|piłę|-|-
hatchet|tool|3|1|1-1|3|hw,wi,ca|hatchet|f|hatchet|-|siekierka|siekierkę|-|-
crowbar|tool|2|0|1-1|2|hw,ra,mi|crowbar|m|crowbar|-|łom|łom|-|-
boltcutters|tool|3|1|1-1|3|hw,ra,mi|crowbar|f|pair of bolt cutters|-|para nożyc do prętów|parę nożyc do prętów|-|-
flashlight|tool|2|0|1-1|2|*|flashlight|f|flashlight|-|latarka|latarkę|-|-
battery|tool|2|0|1-6|1|*|battery|f|battery|batteries|bateria|baterię|baterie|baterii
radio|tool|3|2|1-1|5|of,ra,mi,hs|radio|n|hand-crank radio|-|radio na korbkę|radio na korbkę|-|-
gasmask|tool|3|1|1-1|3|mi,ho,hw|gasmask|f|gas mask|-|maska gazowa|maskę gazową|-|-
compass|tool|2|0|1-1|2|wi,ma,mi|compass|m|compass|-|kompas|kompas|-|-
sewing|tool|2|0|1-1|2|hs,ca,sh|sewing|m|sewing kit|-|zestaw do szycia|zestaw do szycia|-|-
whetstone|tool|1|0|1-1|1|hw,ca,hs|whetstone|f|whetstone|-|osełka|osełkę|-|-
lighter|tool|2|0|1-3|1|*|lighter|f|lighter|lighters|zapalniczka|zapalniczkę|zapalniczki|zapalniczek
matches|tool|1|0|1-3|1|*|matches|n|box of matches|boxes of matches|pudełko zapałek|pudełko zapałek|pudełka zapałek|pudełek zapałek
trowel|tool|1|0|1-1|1|hs,fa|trowel|f|garden trowel|-|łopatka ogrodowa|łopatkę ogrodową|-|-
fishkit|tool|2|0|1-1|2|ma|fishing|m|fishing kit|-|zestaw wędkarski|zestaw wędkarski|-|-
rod|tool|2|0|1-1|2|ma|fishing|f|fishing rod|-|wędka|wędkę|-|-
net|tool|2|0|1-1|3|ma|fishing|f|fishing net|-|sieć rybacka|sieć rybacką|-|-
boathook|tool|1|0|1-1|1|ma|fishing|m|boat hook|-|bosak|bosak|-|-
binoculars|tool|3|1|1-1|3|mi,wi,ma|binoculars|f|pair of binoculars|-|lornetka|lornetkę|-|-
toolbox|tool|3|0|1-1|4|hw,ra,hs|toolbox|f|toolbox|-|skrzynka z narzędziami|skrzynkę z narzędziami|-|-
padlock|tool|1|0|1-2|1|hw,sc,of|key|f|padlock|padlocks|kłódka|kłódkę|kłódki|kłódek
candles|tool|1|0|2-8|1|hs,ca,ht|candle|f|candle|candles|świeca|świecę|świece|świec
lantern|tool|3|1|1-1|3|ca,ht,wi|candle|f|oil lantern|-|latarnia naftowa|latarnię naftową|-|-
tarp|tool|1|0|1-1|2|hw,wi,ma|tarp|f|tarp|-|plandeka|plandekę|-|-
thermos|tool|2|0|1-1|1|hs,wi,of|thermos|m|thermos|-|termos|termos|-|-
pot|tool|2|0|1-1|2|hs,ca,ht|pot|m|cooking pot|-|garnek|garnek|-|-
canopener|tool|2|0|1-1|1|hs,sh|can-opener|m|can opener|-|otwieracz do puszek|otwieracz do puszek|-|-
shovel|tool|2|0|1-1|2|hw,fa,wi|shovel|f|shovel|-|łopata|łopatę|-|-
boots|cloth|3|0|1-1|3|sh,hs,mi|boots|f|pair of boots|-|para butów|parę butów|-|-
hikers|cloth|4|1|1-1|4|sh,ht,mi|boots|f|pair of hiking boots|-|para butów trekkingowych|parę butów trekkingowych|-|-
kidshoes|cloth|2|0|1-1|2|hs,sc,ca|boots|f|pair of kids' shoes|-|para dziecięcych bucików|parę dziecięcych bucików|-|-
socks|cloth|2|0|1-3|1|hs,sh,ca|clothes|f|pair of wool socks|pairs of wool socks|para wełnianych skarpet|parę wełnianych skarpet|pary wełnianych skarpet|par wełnianych skarpet
gloves|cloth|2|0|1-1|2|sh,hw,mi|clothes|f|pair of gloves|-|para rękawic|parę rękawic|-|-
jacket|cloth|3|0|1-1|3|sh,hs,ht|clothes|f|jacket|-|kurtka|kurtkę|-|-
wintercoat|cloth|3|1|1-1|4|sh,hs,ca|clothes|m|winter coat|-|płaszcz zimowy|płaszcz zimowy|-|-
blanket|cloth|2|0|1-2|2|hs,ht,ca|blanket|m|wool blanket|wool blankets|koc wełniany|koc wełniany|koce wełniane|koców wełnianych
sleepingbag|cloth|3|0|1-1|3|wi,hs,ma|blanket|m|sleeping bag|-|śpiwór|śpiwór|-|-
scarf|cloth|1|0|1-1|1|hs,sh,ca|clothes|m|scarf|-|szalik|szalik|-|-
hat|cloth|1|0|1-1|1|hs,sh|clothes|f|knit hat|-|czapka|czapkę|-|-
poncho|cloth|1|0|1-1|1|wi,mi,hw|clothes|f|rain poncho|-|peleryna przeciwdeszczowa|pelerynę przeciwdeszczową|-|-
vest|cloth|4|2|1-1|6|mi|vest|f|bulletproof vest|-|kamizelka kuloodporna|kamizelkę kuloodporną|-|-
backpack|cloth|3|0|1-1|3|sc,sh,hs,mi|backpack|m|backpack|-|plecak|plecak|-|-
belt|cloth|1|0|1-1|1|sh,hs|clothes|m|leather belt|-|pasek skórzany|pasek skórzany|-|-
workpants|cloth|1|0|1-1|2|hw,sh,ra|clothes|f|pair of work trousers|-|para spodni roboczych|parę spodni roboczych|-|-
petrol|fuel|3|1|1-2|3|ra,hw,ma|fuel-can|m|jerry can of petrol|jerry cans of petrol|kanister benzyny|kanister benzyny|kanistry benzyny|kanistrów benzyny
lampoil|fuel|2|0|1-2|2|ca,ht,hs|fuel-can|f|can of lamp oil|cans of lamp oil|puszka oleju do lamp|puszkę oleju do lamp|puszki oleju do lamp|puszek oleju do lamp
firewood|fuel|0|0|1-3|1|wi,hs,ca|firewood|f|bundle of firewood|bundles of firewood|wiązka drewna opałowego|wiązkę drewna opałowego|wiązki drewna opałowego|wiązek drewna opałowego
charcoal|fuel|1|0|1-2|1|ca,hs,fa|firewood|m|bag of charcoal|bags of charcoal|worek węgla drzewnego|worek węgla drzewnego|worki węgla drzewnego|worków węgla drzewnego
propane|fuel|2|0|1-1|3|hs,hw,ht|fuel-can|f|propane bottle|-|butla z propanem|butlę z propanem|-|-
diesel|fuel|3|1|1-1|5|ma,ra,mi|fuel-can|f|barrel of diesel|-|beczka oleju napędowego|beczkę oleju napędowego|-|-
card|trink|2|1|1-3|0|sh,hs,sc|card|f|trading card|trading cards|karta kolekcjonerska|kartę kolekcjonerską|karty kolekcjonerskie|kart kolekcjonerskich
coin|trink|1|0|1-9|0|*|coins|f|old coin|old coins|moneta|monetę|monety|monet
pendant|trink|3|2|1-1|0|*|pendant|m|Firefly pendant|-|wisiorek Świetlików|wisiorek Świetlików|-|-
deck|trink|2|0|1-1|0|hs,ht,mi,sc|cards|f|deck of cards|-|talia kart|talię kart|-|-
chess|trink|2|1|1-1|0|hs,sc,ht|chess|f|chess set|-|szachownica z figurami|szachownicę z figurami|-|-
teddy|trink|2|0|1-1|0|hs,sc|toy|f|teddy bear|-|maskotka pluszowa|maskotkę pluszową|-|-
harmonica|trink|3|1|1-1|0|hs,ht,ca|harmonica|f|harmonica|-|harmonijka|harmonijkę|-|-
guitar|trink|4|2|1-1|0|hs,ht,sh|guitar|f|guitar|-|gitara|gitarę|-|-
musicbox|trink|3|2|1-1|0|hs,ht|music-box|f|music box|-|pozytywka|pozytywkę|-|-
watch|trink|4|2|1-1|0|sh,ht,of|watch|m|working wristwatch|-|zegarek na rękę|zegarek na rękę|-|-
vinyl|trink|4|1|1-3|0|sh,hs|vinyl|f|vinyl record|vinyl records|płyta winylowa|płytę winylową|płyty winylowe|płyt winylowych
photo|trink|1|0|1-1|0|hs,of|photo|f|framed photograph|-|fotografia w ramce|fotografię w ramce|-|-
ring|trink|3|2|1-1|0|hs,ht|ring|f|wedding ring|-|obrączka|obrączkę|-|-
dogtag|trink|2|1|1-3|0|mi|dogtag|m|dog tag|dog tags|nieśmiertelnik|nieśmiertelnik|nieśmiertelniki|nieśmiertelników
toycar|trink|1|0|1-1|0|hs,sc|toy|m|toy car|-|samochodzik zabawkowy|samochodzik zabawkowy|-|-
doll|trink|1|0|1-1|0|hs,sc|toy|f|rag doll|-|lalka szmaciana|lalkę szmacianą|-|-
marbles|trink|1|0|1-1|0|hs,sc|toy|m|bag of marbles|-|woreczek szklanych kulek|woreczek szklanych kulek|-|-
cassette|trink|2|0|1-2|0|hs,sh,sc|tape-cassette|f|cassette tape|cassette tapes|kaseta magnetofonowa|kasetę magnetofonową|kasety magnetofonowe|kaset magnetofonowych
sunglasses|trink|3|0|1-1|0|sh,ht|sunglasses|f|pair of sunglasses|-|para okularów przeciwsłonecznych|parę okularów przeciwsłonecznych|-|-
perfume|trink|4|1|1-1|0|sh,ht,hs|perfume|m|bottle of perfume|-|flakonik perfum|flakonik perfum|-|-
lipstick|trink|3|1|1-1|0|sh,ht,hs|perfume|f|lipstick|-|szminka|szminkę|-|-
buttons|trink|0|0|1-1|0|hs,sh,ca|buttons|m|jar of buttons|-|słoik guzików|słoik guzików|-|-
safekey|trink|2|1|1-1|0|of,sh,ht|key|m|small safe key|-|kluczyk do sejfu|kluczyk do sejfu|-|-
patch|trink|1|0|1-3|0|mi|patch|f|faded WLF patch|faded WLF patches|naszywka WLF|naszywkę WLF|naszywki WLF|naszywek WLF
bible|book|1|0|1-1|0|ca,hs,ho|book|f|bible|-|Biblia|Biblię|-|-
novel|book|1|0|1-2|0|hs,sh,ht|book|f|paperback novel|paperback novels|powieść w miękkiej oprawie|powieść w miękkiej oprawie|powieści w miękkiej oprawie|powieści w miękkiej oprawie
picturebook|book|2|0|1-2|0|hs,sc|book|f|children's picture book|children's picture books|książeczka dla dzieci|książeczkę dla dzieci|książeczki dla dzieci|książeczek dla dzieci
manual|book|2|0|1-1|0|wi,mi,ho|book|m|survival manual|-|podręcznik przetrwania|podręcznik przetrwania|-|-
atlas|book|2|0|1-1|0|ra,ht,of|map|m|road atlas|-|atlas drogowy|atlas drogowy|-|-
trailmap|book|1|0|1-1|0|wi,ht|map|f|trail map|-|mapa szlaków|mapę szlaków|-|-
notebook|book|1|0|1-2|0|sc,of,hs|journal|m|notebook|notebooks|zeszyt|zeszyt|zeszyty|zeszytów
diary|book|2|1|1-1|0|hs,ca,sc|journal|m|diary|-|pamiętnik|pamiętnik|-|-
cookbook|book|2|0|1-1|0|hs,sh|book|f|cookbook|-|książka kucharska|książkę kucharską|-|-
plantguide|book|3|1|1-1|0|wi,ca,fa|book|m|field guide to edible plants|-|atlas roślin jadalnych|atlas roślin jadalnych|-|-
aidmanual|book|2|0|1-1|0|ph,ho,sc|book|m|first-aid manual|-|podręcznik pierwszej pomocy|podręcznik pierwszej pomocy|-|-
schoolbook|book|1|0|1-2|0|sc|book|m|textbook|textbooks|podręcznik szkolny|podręcznik szkolny|podręczniki szkolne|podręczników szkolnych
hymnal|book|1|0|1-1|0|ca|book|m|hymnal|-|śpiewnik|śpiewnik|-|-
newspaper|book|0|0|1-3|0|*|book|f|old newspaper|old newspapers|gazeta|gazetę|gazety|gazet
comic|book|2|0|1-3|0|sh,hs,sc|book|m|comic book|comic books|komiks|komiks|komiksy|komiksów
sheetmusic|book|2|1|1-1|0|hs,sc,ca|book|m|booklet of sheet music|-|zeszyt z nutami|zeszyt z nutami|-|-
tomatoseed|seed|3|0|1-3|2|hs,fa,hw|seeds|f|packet of tomato seeds|packets of tomato seeds|paczka nasion pomidorów|paczkę nasion pomidorów|paczki nasion pomidorów|paczek nasion pomidorów
carrotseed|seed|2|0|1-3|2|hs,fa,hw|seeds|f|packet of carrot seeds|packets of carrot seeds|paczka nasion marchwi|paczkę nasion marchwi|paczki nasion marchwi|paczek nasion marchwi
beanseed|seed|2|0|1-3|2|hs,fa,ca|seeds|m|pouch of bean seeds|pouches of bean seeds|woreczek nasion fasoli|woreczek nasion fasoli|woreczki nasion fasoli|woreczków nasion fasoli
seedpotato|seed|3|1|1-2|3|fa,hs|seeds|m|sack of seed potatoes|sacks of seed potatoes|worek sadzeniaków|worek sadzeniaków|worki sadzeniaków|worków sadzeniaków
mixedseed|seed|2|0|1-1|2|hs,ca,fa|seeds|m|pouch of mixed seeds|-|woreczek nasion|woreczek nasion|-|-
heirloom|seed|4|2|1-1|4|hs,fa,sh|seeds|m|jar of heirloom seeds|-|słoik nasion dawnych odmian|słoik nasion dawnych odmian|-|-
hens|anim|3|1|1-3|3|fa,hs,ca|animal|f|hen|hens|kura|kurę|kury|kur
goat|anim|4|2|1-1|8|fa,ca,hs|animal|f|goat|-|koza|kozę|-|-
rabbits|anim|3|1|1-2|3|fa,hs,ca|animal|f|hutch with rabbits in it|hutches with rabbits in them|klatka z królikami|klatkę z królikami|klatki z królikami|klatek z królikami
beehive|anim|4|2|1-1|6|fa,hs,ca|animal|m|beehive with a living colony|-|ul z żywą rodziną pszczół|ul z żywą rodziną pszczół|-|-
ducks|anim|3|1|2-4|2|fa,wi,ca|animal|f|duck|ducks|kaczka|kaczkę|kaczki|kaczek
piglet|anim|4|2|1-2|4|fa,hs|animal|n|piglet|piglets|prosię|prosię|prosięta|prosiąt
cleankit|part|2|0|1-1|2|mi,hs|gun-part|m|gun cleaning kit|-|zestaw do czyszczenia broni|zestaw do czyszczenia broni|-|-
gunoil|part|2|0|1-1|2|mi,hw,hs|gun-part|f|bottle of gun oil|-|butelka oleju do broni|butelkę oleju do broni|-|-
barrel|part|3|1|1-1|4|mi,hw|gun-part|f|spare barrel|-|lufa zapasowa|lufę zapasową|-|-
scope|part|3|2|1-1|5|mi|gun-part|f|rifle scope|-|luneta|lunetę|-|-
magazine|part|2|0|1-3|2|mi,hs|gun-part|m|spare magazine|spare magazines|magazynek zapasowy|magazynek zapasowy|magazynki zapasowe|magazynków zapasowych
holster|part|2|0|1-1|2|mi,hs|gun-part|f|leather holster|-|kabura skórzana|kaburę skórzaną|-|-
bowstring|part|2|0|1-3|2|ca,wi|gun-part|f|bowstring|bowstrings|cięciwa|cięciwę|cięciwy|cięciw
workparts|part|2|0|1-2|3|hw,*|parts|m|sack of workbench parts|sacks of workbench parts|worek części do warsztatu|worek części do warsztatu|worki części do warsztatu|worków części do warsztatu
"""

# supply group of each category: what the item adds to (clan_supply category); '' = morale only
GROUP = {"food": "food", "seed": "food", "anim": "food", "water": "water", "med": "med", "ammo": "ammo",
         "mat": "mat", "tool": "mat", "cloth": "mat", "fuel": "mat", "part": "mat", "trink": "", "book": ""}
# icon the launcher has (release/launcher/src/clan-icons.js) for a category when the item's own icon is missing
FALLBACK_ICON = {"food": "food", "seed": "food", "anim": "food", "water": "water", "med": "medicine", "ammo": "ammo", "mat": "materials", "tool": "wrench",
                 "cloth": "rag", "fuel": "canister", "part": "parts", "trink": "keepsake", "book": "journal"}
TIERS = ("scraps", "poor", "normal", "good", "luxurious")
