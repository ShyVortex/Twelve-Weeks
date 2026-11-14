"""Static data of the clan feed generator: names, roles, illnesses, places, vocabulary, and the 2013 ticker pools.
Sources of the 2013 data: re/factions2013/clan-feed.md (PS3 net10.bin `*first-name-list*` / `*last-name-list*` / `*healthy|hungry|sick|dead-member-list*`
resolved against the English text bank 2.networking)."""

# --- 2013 `*first-name-list*` (92 entries in the game, de-duplicated, the two developer-joke entries left out) and `*last-name-list*`
FIRST_2013 = [
    "Jeff", "Evan", "Dan", "Bill", "Craig", "John", "William", "Nancy", "Karen", "Aaron", "Joe", "Arnaldo", "Trevor", "Robert", "Claire", "Alison",
    "Raul", "Adam", "Adrian", "Alex", "Amy", "Andres", "Ana", "Malcolm", "Carson", "Carlos", "David", "Rodney", "Olivia", "Jennifer", "Sandra",
    "Chris", "Kion", "Troy", "Beverly", "Ryan", "Nara", "Jin", "Tyler", "Anthony", "Kurt", "Eric", "Jacob", "Justin", "Bruce", "Neil", "Peter",
    "Sofia", "Mia", "Isabella", "Santiago", "Mateo", "Diego", "Ricky", "Quentin", "Artem", "Christian", "Jeremy", "Corin", "Lauren", "Edward", "Max",
    "Kan", "Aliyah", "Jordan", "Kayla", "Madison", "Cameron", "Ethan", "Kevin", "Jane", "Mike", "Michael", "Damon", "Cynthia", "Jose", "Spencer",
    "Stephanie", "Sean", "Ava", "Alexander", "Aiden", "Ivan", "Lars", "Bernard", "Simon", "Scott", "Maria", "Matthew"]
LAST_2013 = [
    "Shaffer", "Rogers", "Smith", "Russel", "Peters", "Simonson", "James", "Bryant", "Ibanez", "Stevens", "Cho", "Lin", "Brown", "De Silva", "Kim",
    "Singh", "Nakata", "Lee", "Espino", "Ly", "Lam", "Vasquez", "Park", "Newman", "Goldman", "Saito", "Tanaka", "Garcia", "Rodriguez", "Martinez",
    "Diaz", "Chong", "Choi", "Wong", "Chan", "Chen", "Ng", "Cheung", "Nguyen", "Tran", "Castillo", "Reyes", "Santos", "Ahmadi", "Cook", "Khan", "Patel",
    "Shah", "Williams", "Jackson", "Davis", "Walker", "Carter", "Anderson", "Ramirez", "Thomas", "Martin", "Dubois", "Kowalski", "Nowak", "Jones",
    "Bauer", "Moser", "Lukic", "Petrovic", "Jensen", "Salo", "Karlsson", "Leroy", "Schmidt", "Fischer", "Vlahos", "Nagy", "Varga", "Murphy", "Murray",
    "Wilson", "Johnson", "Clark", "Mitchell", "Campbell", "Parker", "Cohen", "Levi"]

# Extra names (the 2013 list is short and US/Asian-heavy; the mod's clan can reach hundreds of people). (name, gender f/m)
EXTRA_WLF = [("Marcus", "m"), ("Danny", "m"), ("Rosa", "f"), ("Hector", "m"), ("Tasha", "f"), ("Wes", "m"), ("Gina", "f"), ("Luis", "m"), ("Frank", "m"),
             ("Agnes", "f"), ("Omar", "m"), ("Pete", "m"), ("Nina", "f"), ("Cole", "m"), ("Beth", "f"), ("Reggie", "m"), ("Lila", "f"), ("Hank", "m"),
             ("Priya", "f"), ("Mo", "m"), ("Tomas", "m"), ("Gabe", "m"), ("Joanne", "f"), ("Sam", "n"), ("Yuki", "f"), ("Dee", "f"), ("Rudy", "m"),
             ("Carla", "f"), ("Ben", "m"), ("Leah", "f"), ("Walt", "m"), ("Imani", "f"), ("Theo", "m"), ("Kit", "n"), ("Rhea", "f"), ("Paulie", "m"),
             ("Vera", "f"), ("Nico", "m"), ("Lucia", "f"), ("Bo", "m"), ("Tamsin", "f"), ("Jonas", "m"), ("Odile", "f"), ("Hiro", "m"), ("Wendy", "f"),
             ("Dmitri", "m"), ("Faye", "f"), ("Ollie", "m"), ("Marta", "f"), ("Cal", "m"), ("Jules", "n"), ("Rafael", "m"), ("Shirin", "f"), ("Gus", "m")]
EXTRA_SERA = [("Jude", "m"), ("Oona", "f"), ("Mara", "f"), ("Elias", "m"), ("Jonah", "m"), ("Ruth", "f"), ("Silas", "m"), ("Hannah", "f"), ("Gideon", "m"),
              ("Tobias", "m"), ("Naomi", "f"), ("Asa", "m"), ("Edda", "f"), ("Soren", "m"), ("Ilse", "f"), ("Anselm", "m"), ("Bryn", "n"), ("Hollis", "m"),
              ("Tamar", "f"), ("Caleb", "m"), ("Thea", "f"), ("Ezra", "m"), ("Lydia", "f"), ("Abel", "m"), ("Esther", "f"), ("Ivo", "m"), ("Petra", "f"),
              ("Nils", "m"), ("Greta", "f"), ("Aldo", "m"), ("Miriam", "f"), ("Orrin", "m"), ("Wren", "n"), ("Hale", "m"), ("Mina", "f"), ("Cade", "m"),
              ("Liora", "f"), ("Ansel", "m"), ("Odessa", "f"), ("Rafe", "m"), ("Ingrid", "f"), ("Jory", "m"), ("Kasimir", "m"), ("Bethany", "f"),
              ("Matthias", "m"), ("Selah", "f"), ("Emrys", "m"), ("Noor", "f"), ("Teodor", "m"), ("Anika", "f"), ("Rowan", "n"), ("Bram", "m"), ("Una", "f")]
FEMALE_2013 = {"Nancy", "Karen", "Claire", "Alison", "Amy", "Ana", "Olivia", "Jennifer", "Sandra", "Beverly", "Nara", "Sofia", "Mia", "Isabella", "Lauren",
               "Aliyah", "Kayla", "Madison", "Jane", "Cynthia", "Stephanie", "Ava", "Maria"}
NEUTRAL_2013 = {"Jordan", "Cameron", "Kan", "Kion", "Jin", "Max", "Corin", "Alex"}

# roles: key -> (label WLF, label Seraphites, weight)
ROLES = {
    "scavenger": ("scavenger", "forager", 22), "medic": ("medic", "healer", 8), "cook": ("cook", "cook", 8), "guard": ("guard", "watch", 16),
    "mechanic": ("mechanic", "toolmaker", 8), "scout": ("scout", "archer", 10), "gardener": ("gardener", "gardener", 8), "kid": ("kid", "child", 10),
    "elder": ("old-timer", "elder", 6), "radio": ("radio operator", "weaver", 4),
}

# illnesses: key -> (name, name with article, cure, weight when caused by hunger, weight after a fight)
ILLNESS = {
    "bronchitis": ("bronchitis", "bronchitis", "antibiotics", 18, 3),
    "infected_wound": ("infected wound", "an infected wound", "antibiotics and clean bandages", 6, 20),
    "fever": ("fever", "a fever", "fever reducers", 16, 6),
    "dysentery": ("dysentery", "dysentery", "antibiotics and clean water", 14, 1),
    "pneumonia": ("pneumonia", "pneumonia", "strong antibiotics", 12, 2),
    "broken_leg": ("broken leg", "a broken leg", "a proper splint and painkillers", 4, 6),
    "spores": ("spore sickness", "spore sickness", "a miracle", 8, 5),     # canon: no cure, no recovery (clan_story_spores.py); a mask on hand makes it rarer
    "flu": ("flu", "the flu", "fever reducers", 15, 2),
}

FACTION = {
    "W": {"name": "WLF", "plural": "Wolves", "enemy": "Scars", "enemies": "Scars", "leader": "Isaac",
          "places": ["stadium", "checkpoint", "FOB", "east barracks", "loading dock", "old gym", "pharmacy block"]},
    "S": {"name": "SERAPHITES", "plural": "Seraphites", "enemy": "Wolves", "enemies": "Wolves", "leader": "the Prophet",
          "places": ["island", "long house", "kitchen house", "harbor", "weaving house", "settlement", "shore camp"]},
}
INFECTED = ["runner", "clicker", "stalker", "shambler", "bloater"]

# Words a faction's voice must never use (checked by tools/tests/test_clan_story.py over every line a faction can draw)
BANNED_SERA = ["jesus", "christ", "god", "lord", "isaac", "stadium", "fob", "scars", " scar ", "wlf", "checkpoint", "barracks", "radio chatter"]
BANNED_WOLF = ["prophet", "her light", "seraphite", "elders", "the island", "healer", "sisters", "brothers"]
BANNED_SHARED = BANNED_SERA + BANNED_WOLF + ["amen"]

# --- 2013 ticker (re/factions2013/clan-feed.md). "[TEXT]" -> {A}. Weighted lists as in the game: healthy = 13 x "is healthy" + the rest.
TICKER_HUNGRY = [
    "{A} is starving.", "{A} is beginning to feel faint.", "{A} is desperate for food.", "{A} is gnawing on rat bones.",
    "{A} has terrible hunger pains.", "{A} can barely walk.", "{A} is very malnourished.", "{A} has lost 15 pounds from malnourishment.",
    "{A} is starting to consider cannibalism.", "{A} is considering eating the cat.", "{A} is trying not to think about food.",
    "{A} is accusing others of hoarding food.", "{A} is too weak to work."]
TICKER_SICK = [
    "{A} is sick.", "{A} has started praying.", "{A} has got the shakes.", "{A} did not get up from bed this morning.",
    "{A} has been coughing a lot lately.", "Gangrene is beginning to set in for {A}.", "{A} needs antibiotics right away.",
    "{A} is starting to look pretty far gone.", "Everyone's getting worried about {A}.", "No one is sure how much longer {A} can hang on.",
    "The situation for {A} is looking pretty bad.", "{A} caught botulism from a can of old food.", "{A} has a severe infection.",
    "{A} has an intense fever.", "{A} can't stop coughing.", "{A} hasn't slept in days.", "{A} had a mental breakdown.",
    "{A} is having a severe allergic reaction.", "{A} is coughing up blood.", "{A} has symptoms of pneumonia.", "{A} has a serious concussion.",
    "{A} is having severe hallucinations.", "{A} may have become infected.", "{A} is showing early signs of scurvy.",
    "{A} is shivering and feverish.", "{A} may require an amputation.", "{A} has a severe flu.", "{A} has contracted dysentery."]
TICKER_HEALTHY = (["{A} is healthy."] * 13) + [
    "{A} caught a rabbit.", "{A} is learning guitar.", "{A} is learning to sew.", "{A} is building a new lookout perch for the camp.",
    "{A} is upgrading the water filtration system.", "{A} is digging a new latrine.", "{A} caught a fish.", "{A} is grilling a rat.",
    "{A} is skinning a deer.", "{A} is repairing the north fence.", "{A} is repairing the west fence.", "{A} is repairing the east fence.",
    "{A} is repairing the south fence.", "{A} is digging an evacuation tunnel.", "{A} is learning first aid.", "{A} is repairing the water collector.",
    "{A} is frying some fish.", "{A} is skinning a racoon.", "{A} is reinforcing the main gate.", "{A} is reinforcing the rear gate.",
    "{A} is washing clothes.", "{A} is mending clothes.", "{A} is checking the ammunition supply.", "{A} is keeping a close watch on the main road.",
    "{A} is doing a shift in the lookout perch.", "{A} is cleaning some fish.", "{A} is tying fishing lures.", "{A} caught a raccoon.",
    "{A} is building rat traps.", "{A} is learning fly-fishing.", "{A} is working in the garden.", "{A} is planting kale in the garden.",
    "{A} is pulling weeds in the garden.", "{A} is repairing the generator.", "{A} is spit-roasting a raccoon.", "{A} is refueling the generator.",
    "{A} is repairing the ethanol still.", "{A} is emptying the ethanol still.", "{A} has a rosy complexion.", "{A} is scouting the surrounding area.",
    "{A} is exercising.", "{A} is sharpening a machete.", "{A} is setting up perimeter alarms.", "{A} is cleaning the latrine.",
    "{A} is gathering nuts and berries.", "{A} is taking inventory.", "{A} is starting a fire for dinner.", "{A} is making moonshine.",
    "{A} is learning to paint.", "{A} is making bombs.", "{A} had enough to eat this morning.", "{A} is whittling.", "{A} is going foraging.",
    "{A} found some old books.", "{A} is asleep.", "Things are looking up for {A}.", "{A} is contemplative.", "{A} is reading old medical books.",
    "{A} is making a map of the area.", "{A} is sharpening arrows.", "{A} is building a chicken coop.", "{A} is repairing fishing nets.",
    "{A} is telling stories by the fire.", "{A} is pickling vegetables.", "{A} is fetching water.", "{A} is smoking meat.", "{A} is setting rabbit traps.",
    "{A} is collecting wood for the fires.", "{A} went hunting.", "{A} went fishing.", "{A} found a soccer ball.", "{A} is restringing a bow.",
    "{A} is learning botany.", "{A} is foraging for berries.", "{A} found an old cookbook.", "{A} is learning to make jerky."]
TICKER_DEAD = ["{A} has died."]
# rare inside joke: replaces a sick ticker line about 1 time in 70 - uncommon, not secret
TICKER_RARE_SICK = "{A} ate shit and fell ill to HIV."
TICKER_RARE_CHANCE = 0.015

TICKER_NOT_SERA = ("generator", "ethanol", "filtration", "moonshine", "ammunition", "bombs", "machete", "perimeter alarms", "soccer")
