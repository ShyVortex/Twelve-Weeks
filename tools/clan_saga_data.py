"""Data of the clan saga (tools/clan_saga.py): the places of every map, what a person carries and fears, injuries, weapons.  English only.

MAPS[display name] = {"places": [rooms / streets / shops], "air": [what the place smells or sounds like, fits "the smell of {air}" / "the sound of {air}" via 'air' text]}
Every 'air' entry is a noun phrase that follows "the smell of" or "the sound of" as the template says, so entries are tagged: ("s", "...") smell, ("h", "...") sound.
"""

MAPS = {
    "Forest": {"places": ["the fallen fir over the creek", "the hunting blind", "the deer trail", "the mossy culvert", "the burned cabin"],
               "air": [("s", "wet moss and fir sap"), ("h", "a creek running under ice"), ("s", "old woodsmoke")]},
    "Gas Station": {"places": ["the pump island", "the cooler aisle", "the garage bay", "the dumpster yard", "the roof sign"],
                    "air": [("s", "old petrol and rat droppings"), ("h", "a loose sign knocking in the wind"), ("s", "burnt rubber")]},
    "School": {"places": ["the gym", "the east stairwell", "the cafeteria", "the principal's office", "the bus loop"],
               "air": [("s", "floor wax and mildew"), ("h", "a locker door swinging on one hinge"), ("s", "chalk dust and damp paper")]},
    "Shipyard": {"places": ["the crane cab", "the container maze", "the dry dock", "the welding shed", "the east pier"],
                 "air": [("s", "rust and tar"), ("h", "chains ringing against a hull"), ("s", "diesel and cold salt")]},
    "Resort": {"places": ["the pool deck", "the lobby bar", "the boathouse", "the golf cart shed", "the east chalets"],
               "air": [("s", "chlorine long gone green"), ("h", "a banner flapping above the lobby"), ("s", "mildewed carpet")]},
    "Seraphite Camp": {"places": ["the cistern", "the prayer hall", "the rope bridge", "the smokehouse", "the weaving shed"],
                       "air": [("s", "smoked fish and lamp oil"), ("h", "wind through the rope bridge"), ("s", "wet cloth and ash")]},
    "Houses": {"places": ["the corner house", "the garage", "the back fence", "the porch with the swing", "the cellar stairs"],
               "air": [("s", "damp curtains and cat"), ("h", "a screen door slapping"), ("s", "cold ash in a fireplace")]},
    "Hospital": {"places": ["the east ward", "the pharmacy cage", "the lobby atrium", "the morgue corridor", "the ambulance bay"],
                 "air": [("s", "old disinfectant and something sweeter underneath"), ("h", "a gurney wheel squealing somewhere"), ("s", "mould in the ceiling tiles")]},
    "Hardware Store": {"places": ["the paint aisle", "the nail bins", "the loading dock", "the lumber yard", "the key-cutting counter"],
                       "air": [("s", "cut pine and machine oil"), ("h", "loose screws rolling over concrete"), ("s", "dried paint")]},
    "Motel": {"places": ["room nine", "the ice machine", "the front office", "the dry pool", "the parking lot"],
              "air": [("s", "stale cigarettes and cheap carpet"), ("h", "a vending machine humming to nobody"), ("s", "bleach on old stains")]},
    "Hillcrest": {"places": ["the water tower", "the church steps", "the bakery", "the cul-de-sac", "the clinic basement"],
                  "air": [("s", "cold stone and rain"), ("h", "a church bell with no rope"), ("s", "burnt flour")]},
    "TV Station": {"places": ["the studio floor", "the control room", "the antenna stairs", "the green room", "the car park"],
                   "air": [("s", "hot dust and old cables"), ("h", "static from a monitor that still has power"), ("s", "stale coffee")]},
    "Train Station": {"places": ["the ticket hall", "the platform", "the baggage cage", "the signal box", "the footbridge"],
                      "air": [("s", "rust and pigeon dung"), ("h", "water dripping on the rails"), ("s", "cold iron")]},
    "Downtown": {"places": ["the bank lobby", "the bus lanes", "the fountain square", "the parking garage", "the tram wire alley"],
                 "air": [("s", "brick dust and wet glass"), ("h", "traffic lights ticking over for no one"), ("s", "old fires")]},
    "Lodge": {"places": ["the great hall", "the antler stairs", "the boat shed", "the trophy room", "the long porch"],
              "air": [("s", "cold hearth and elk hide"), ("h", "a shutter creaking in the lake wind"), ("s", "pine resin")]},
    "Jackson Suburbs": {"places": ["the cul-de-sac", "the playground", "the snowed-in garage", "the gate wall", "the stranded school bus"],
                        "air": [("s", "snow melting on warm stone"), ("h", "a swing chain creaking"), ("s", "woodsmoke and horse")]},
    "Suburbs": {"places": ["the cul-de-sac", "the three-car garage", "the back porch", "the kitchen with the bay window", "the mailbox row"],
                "air": [("s", "mould in carpet and cat"), ("h", "a distant dog that is not a dog"), ("s", "damp drywall")]},
    "Bookstore": {"places": ["the poetry shelves", "the cafe counter", "the stock room", "the upstairs gallery", "the display window"],
                  "air": [("s", "mildewed paper and spilled coffee"), ("h", "pages rustling in a draught"), ("s", "dust and glue")]},
    "Hillside": {"places": ["the gate", "the switchback road", "the chapel", "the retaining wall", "the lookout"],
                 "air": [("s", "wet clay and rust"), ("h", "gravel sliding down the slope"), ("s", "cold pine")]},
    "Capitol Hill Shops": {"places": ["the record store", "the bakery", "the laundromat", "the awning row", "the back alley"],
                           "air": [("s", "stale bread and vinyl"), ("h", "a loose awning drumming in the wind"), ("s", "old soap")]},
    "Convention Center": {"places": ["the escalators", "the exhibition hall", "the loading ramp", "the registration desks", "the catwalk"],
                          "air": [("s", "dust and carpet glue"), ("h", "footsteps carried a hundred yards by the concrete"), ("s", "mould")]},
    "Overpass": {"places": ["the collapsed span", "the bus on its side", "the guardrail", "the underpass", "the toll booth"],
                 "air": [("s", "wet concrete and exhaust long gone"), ("h", "wind whistling through rebar"), ("s", "old tar")]},
}
GENERIC = {"places": ["the main hall", "the back stairs", "the yard", "the loading door", "the roof"],
           "air": [("s", "dust and mould"), ("h", "a loose sheet of tin banging"), ("s", "cold ash")]}

# (site, how it is bound)
SITES = ["left eyebrow", "right shoulder", "left forearm", "ribs", "right thigh", "scalp", "left hand", "calf", "right ankle", "jaw", "left shoulder", "palm"]
CLOTHS = ["a strip of bedsheet", "boiled rag", "gauze that was washed twice", "a torn shirt sleeve", "waxed cord and a clean sock", "a bandage with a stain the colour of tea"]
# role -> what a bad limb forbids
JOBS = {"scavenger": "carry a full sack", "medic": "hold the lamp steady", "cook": "lift the big pot", "guard": "walk the wall", "mechanic": "work the vice",
        "scout": "climb the roof", "gardener": "dig the beds", "kid": "chase the others", "elder": "take the stairs", "radio": "turn the crank"}
# what hurt a person: (cause with enemy name placeholder)
CAUSES = ["a {enemy_n} bullet", "a {enemy_n} hatchet", "a bolt from a {enemy_n} bow", "a splinter of a nail bomb", "the edge of a broken bottle", "a {enemy_n} knife",
          "a {enemy_n} pipe", "a shotgun blast from a {enemy_n}"]
POSSESSIONS = ["a dead watch", "a photograph with the face worn off", "a tin whistle", "a lucky bullet on a string", "a pocket knife with a cracked handle",
               "a child's shoe", "a scrap of blue ribbon", "a notebook with half the pages gone", "a dented lighter", "a jar of buttons", "a folded map of a place long gone",
               "a wedding ring on a shoelace", "a ceramic cup with no handle", "a harmonica key", "a pair of reading glasses held with tape", "a postcard of the sea",
               "a plastic dinosaur", "a pair of boots too big for anyone", "a compass that points a little east of north", "a pencil worn to a nub"]
FEARS = [("the dark", "puts a hand on the wall before every corridor"), ("water", "will not cross the creek unless somebody is holding the rope"),
         ("fire", "flinches at every struck match"), ("dogs", "walks around the kennel yard rather than through it"),
         ("tall grass", "never walks through it without a stick"), ("closed doors", "props every door open with a boot"),
         ("clickers", "freezes whenever a tap drips twice in the same rhythm"), ("being alone", "sleeps next to the stove where the others pass"),
         ("heights", "takes the long way around any stair with a gap"), ("the quiet", "hums when the room goes silent")]
WEAPONS = {"bow": ("the bow", "arrows"), "revolver": ("the revolver", "rounds"), "shorty": ("the shorty", "shells"), "hunting": ("the hunting rifle", "rounds"),
           "semi": ("the semi-auto rifle", "rounds"), "burst": ("the burst rifle", "rounds"), "pistol": ("the 9mm", "rounds"), "crossbow": ("the crossbow", "bolts"),
           "melee": ("a length of pipe", "swings"), "bomb": ("nail bombs", "bombs"), "molotov": ("molotovs", "bottles")}
