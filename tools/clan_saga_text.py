"""Text of the clan saga (tools/clan_saga.py): the long, match-tied entries of the clan chronicle.  English only (the Polish clan screens show these rows in English).

TEXT is parsed by clan_saga.pools(): "== pool.name" starts a pool, every following non-empty line is one template (one sentence, or two short ones).  A leading
"W:" / "S:" limits the template to the Wolves / the Seraphites.  Placeholders: {A} {B} {C} {D} names, {A_he} {A_He} {A_his} {A_him} {A_himself}; {map} {place} {place2}
{air} {camp} {enemy} {enemies} {leader} {k} {ex_p} {rv_p} {hs_p} {dn_p} {dt_p} {wpn} {site} {cloth} {job} {cause} {item_pl} {loot_list} {kd} {kmap} {kplace} {kd_ago}
{kitem} {n} {prev_map} {prev_res} {AW} {dpos} ... A template whose placeholder has no value today is not used (a day without that datum never prints a hole).
"""
TEXT = r"""
== loss.title
{A} met you at the gate and did not ask
Nobody sang after {map}
{enemies} held {map}, and we paid for it
{map} is lost
Supper was quiet after {map}
A bad evening at {map}
{A} counted the rifles twice
== loss.event
{map} went to {enemies}. You got out through {place} with {k} of them down on the board, not nearly enough to matter, and {smell} in your clothes.
You fell back from {place2} of {map} when the line broke, with {enemies} behind you and a locked door ahead, and the door gave only after the third kick.
We lost at {map}. You counted {k} down on their side; the last stand was at {place}, and the last thing you saw was the floor coming up.
{map} was not kind. {place} held {enemies}' best, and by the time the push reached {place2} there was no push left to speak of.
You went out of {map} backwards, one fist in somebody's belt, with {enemies} cheering from {place} and your own breath loud as a saw.
A loss at {map}: {k} down, a long crawl back through {place2}, and a quiet where the last orders should have been.
== loss.camp
{A} sat by the stove peeling a potato into one long ribbon, over and over, and did not eat any of it.
{A} washed the blood from your hands in a basin; the water went pink, then cold.
{A} counted the rifles on the rack twice and found them all there, which only made it worse.
Somebody turned the radio off, and no one turned it on again.
The kids were sent to bed early and lay with their ears against the wall.
{A} snapped at {B} over a spoon, and apologised for it with a whole slice of bread.
== loss.b
{B} said it was {place2} that did it, the way it is always the ground and never the legs.
{B} wanted to go back out tonight and was told no by three different people.
{B} took the first watch and refused to be relieved.
{B} said nothing, which was loud enough.
{B} cleaned the same rifle until the bolt shone, and then cleaned it again.
== loss.streak
It is {lossw} lost in a row now, and the chalk board by the door has stopped being kept up.
That is two losses in a row, and the mess has noticed it.
After {prev_map}, {map}. People are counting, and they do not like the sum.
== loss.recover
It was {prev_map} that went wrong yesterday as well; {A} muttered that bad luck is only a habit that has not been broken yet.
== down.title
{A} sewed your {site} shut in {camp}
Down {dn_p} at {map}, and {A} counts the bruises
{A} picked glass out of your wounds
{A} would not let you sleep until the shaking stopped
{A} kept the tally on your ribs
== down.event
You went down {dn_p} in {map}, the last time flat on your face at {place} with {enemies} standing over you and {wpn} out of reach.
You were put on the ground {dn_p} at {map}; once you crawled, once you were dragged by the collar out of {place}, once you simply lay there.
{map} dropped you {dn_p}. The last time left you looking at the ceiling of {place} and listening to your own heartbeat go soft.
You hit the floor of {place} of {map} {dn_p}, and each time somebody's hands found you before {enemies} did.
Down at {place}, up again, down at {place2}: {dn_p} in {map} before it was over.
Your vest took what it could in {map}, and when it could not any more you went down {dn_p}, at {place} and then at {place2}.
== down.care
{A} cut away the sleeve, flushed the wound from a kettle that was too hot, and sewed it with fishing line, eleven stitches, tight and ugly.
{A} held the lamp low, tweezers in the other hand, and drew a splinter of glass out of your {site} that had gone in under the skin and kept going.
{A} pressed two fingers into the bruise at your ribs until you swore, then nodded and said nothing is broken, only offended.
{A} bound the {site} with {cloth} and tied the knot twice, the way {A_he} ties everything now.
{A} peeled the shirt off the dried blood a little at a time with warm water and talked about nothing the whole time, so that you would not feel it.
{A} stitched the cut and told the kids you had walked into a door.
== down.after
Nobody asked how it went. They looked at the stitches instead, and went back to their soup.
The kids lined up to touch the bruise and were told they could look, not poke.
{B} brought a tin cup of something warm and left it by your hand.
{B} pulled your boots off for you and set them by the door where you would find them.
{B} said it looked worse than it was, which is what everyone says to someone who looks like that.
{A} says the scar will suit you.
== down.you
Your {ysite}, stitched after {ymap} on day {yd}, was the first thing {A} looked at. It had held.
The cut from {ymap} (day {yd}) opened a thumb's width again, and {A} said what {A_he} thought of that, at length.
== win.title
{map} taken, and {A} is not hiding the grin
We held {map}
{A} banged a ladle on the pot for {map}
A good night at {map}
{map} was ours by dark
{A} had the kettle on before you reached the gate
== win.event
{map} fell to you: {k} down, and the last of {enemies} gave up {place} at dusk with the sun in their eyes.
You held {place} of {map} against {enemies} until they stopped coming, with {k} on the ground by the end and your ears ringing like a bell.
A win at {map}. {k} of them down, and you walked out through {place2} like someone with somewhere to be.
You took {map} room by room, {place} first and then {place2}, and when it was quiet you could hear water dripping onto something that was not metal.
{enemies} came through {place} of {map} in a rush and you were there, {k} down to show for it, a run you could not have planned.
You cleared {enemies} out of {place} of {map} for the last time that day, {k} down all told, and sat on the stairs for a minute with {air} around you.
== win.camp
{A} hung your jacket by the stove and pretended not to look at the holes in it.
The kids acted the whole thing out with sticks in the yard, and {enemies} lost every time.
{A} cut the heel of the loaf for you, the piece everybody wants.
Somebody found a candle end and lit it, for no reason anyone offered.
{A} said it out loud: another day no one has to dig for.
Even {A}, who does not do this, laughed at something {B} said and could not say what.
== win.hs
{hs_p} among them, and {A} wants to hear that part again, slowly.
{hs_p}, and {A} keeps saying the number like a prayer.
== win.after_loss
After {prev_map} yesterday, {A} did not dare believe it, and made you say it twice.
After {prev_map}, this felt like cold water on a burn.
== win.big
{A} tied a knot in the cord above the door, one more for the days that went well, and there are more knots than anyone expected.
== exec.title
{ex_p} at {map}, and {A} will not meet your eyes
{A} asked what {map} was like, and you did not say
What you did at {place}
{A} scrubbed your sleeve in cold water for an hour
== exec.event
You finished {ex_p} on the floor of {place} of {map}, up close, with a knife, and the sound was wetter than you remembered.
{ex_p} in {map}. One of them looked up at you at {place} and spat, and you did it anyway.
In {map} you did the slow thing {ex_t}: a knee in the back, a hand over the mouth, and {place} went red to the baseboards.
Three seconds each, no more, {ex_p} in all, at {place2} of {map}. It is never as quick as it sounds.
You put a throat open at {place} of {map} and held it while it finished, and then another, {ex_p} before the evening was done, {smell} turned to copper.
== exec.react
{A} took your sleeve, soaked it in cold water and worked at the dark stiff patches with a brush until the skin on {A_his} knuckles split.
{B} moved down the bench by a hand's width, then felt ashamed and moved back.
The kids heard and asked, and {A} said it was a thing grown-ups do so children can keep their toys, which satisfied no one.
{A} said that is how it is, in a flat voice, and then went outside for a long time.
Nobody commented at supper. The ladle scraped the pot.
== rev.title
You carried {rv_p} out of {map}
{A} is counting the people you pick up
{A} wants to know how many hands you got to
== rev.event
You got {rv_p} back on their feet at {map}, once under fire at {place}, with bullets cutting plaster from the wall above your heads.
You hauled {rv_p} up in {map}, and crawled the last ten feet to {place2} on your elbows to reach the third, your mouth full of dust.
You pulled {rv_p} up off the ground at {map}. One of them was bleeding through the fingers and said thank you three times without hearing it.
== rev.react
{A} wrote it down, not the kills but the pick-ups. It is a different column, and {A} says it is the one that counts.
{A} tied a knot in a cord for each person you hauled up and hung the cord above your bunk.
{B} said you could have stayed behind cover, and then said thanks in the same breath so you could not argue.
== quiet.title
{map}: the usual, and the usual is enough
Nothing remarkable at {map}
A plain day at {map}
{A} asked about {map}, and you shrugged
== quiet.event
You spent the evening at {map}: {k} down, nothing pretty and nothing worth a story, just {place} and the long walk back past {place2}.
Nothing broke at {map}. {k} down, a long wait at {place}, and {air}.
{map} gave you {k} down and an afternoon of {air}; you came home with wet boots and an empty head.
You were back from {map} before the lamps: {k} down, a cold hand, an honest day's work.
== quiet.camp
{A} did not press for details, and handed you a bowl.
{camp} smelled of boiled onions and wet wool.
Somebody had mended your strap while you were out.
{A} showed you a drawing the kids made of you, in which you have too many arms.
== bridge.same_map
It is {map} again, {nth} time this week, and {A} knows {place} by its cracks now.
{map} again. {A} said the ground there must be getting tired of the sight of you.
== bridge.you_scar
Your {ysite}, stitched after {ymap} on day {yd}, has settled down to a pink line.
== hurt.line
{B} came back from {map} with {B_his} {site} laid open by {cause}, white to the bone, and sat down very carefully on the nearest crate.
{B} limped in behind you, {B_his} {site} ruined by {cause} at {place2}, and refused to be carried.
{B} took {cause} in the {site} at {place2}; {A} cut away the sleeve and went quiet at what was underneath.
== mark.line
{A} wrapped {B}'s {site} in {cloth} and said it would be days before {B} could {job}.
== haul.title
{A} turned the sack from {map} out on the floor
What {map} gave us
{A} counted {map} haul twice
Inventory after {map}
{A} made a list of what came back from {place}
{A} laid {map} haul out in rows
== haul.found
In the sack from {place}: {loot_list}.
From {place2}, wrapped in somebody's old shirt: {loot_list}.
{map} gave up {loot_list}, most of it from {place}.
{loot_list}, said the tally, all of it out of {place}.
== haul.food
The cans were dented and labelless; {A} shook one by the ear, grinned, and wrote an optimistic guess on the lid in grease pencil.
{A} sniffed an open tin the way other people read a letter.
The food goes straight to the pot, and {A} has already decided who gets the first ladle.
== haul.med
{A} sorted the medicine by how scared it should make us; the antibiotics went into the lockbox, the rest in the cupboard.
{A} lined up the dressings and counted aloud, as if repetition could make more of them.
== haul.ammo
{A} fed the rounds into a coffee tin one by one, and the sound was almost pleasant.
{A} divided the rounds into twists of paper, five to a twist, and wrote the number on each in pencil.
== haul.tool
{A} held the find up to the lamp and smiled for the first time all week.
{A} turned the tool over and over, saying what it was for in a low, loving voice.
== haul.keep
{B} claimed {kitem_a} for the kids before the sack was even closed.
{A} put {kitem_a} on the shelf above the stove, where everyone could see it and no one could pretend it was not there.
== use.title
{A} spent some of the {item_pl} from {kmap}
Remember the {item_short} from {kplace}?
{A} opened what you brought home on day {kd}
== use.ammo
{A} spent {n} of the {item_pl} from {kmap} (found {kd_ago}) on target practice behind the wall, and every shot was a lesson.
{A} counted what was left of the {item_pl} from {kplace}: {n_left}. It will not last the month, and {A_he} said so aloud.
== use.food
{A} cooked the {item_pl} from {kplace} for the evening meal and said a grace nobody had asked for.
{A} opened the last of the {item_pl} from {kmap}, saved since day {kd}, and shared it spoon by spoon with the kids.
== use.med
{A} used one of the {item_pl} from {kplace} and wrote it in the ledger with a small, regretful stroke.
{A} opened the last of the {item_pl} from {kmap} for a fever that would not break.
== use.tool
{A} used the {item_pl} from {kplace} (day {kd}) to fix what had been broken since spring, and then went looking for the next thing.
{A} was proud of the {item_pl} from {kmap}, and showed it to everyone who sat still.
== keepcb.title
The {kitem} from {kmap} turns up again
{A} and the {kitem}
Day {kd}'s {kitem} is still in use
== keepcb.chess
The chessboard from {kplace} (day {kd}) has grown a tournament. {A}, who was too proud to learn the rules, lost to a six-year-old and took it with dignity.
{A} found the missing black knight in the dust under the stove and slid it back on the chessboard from {kmap} without a word.
== keepcb.guitar
{A} learned a three-note riff on the string from {kplace}, one that sounds like a door; the kids hum it to each other from room to room.
== keepcb.comic
The comic from {kplace} is on its fortieth reading; {A} does the voices, and the kids are getting too old to be fooled but come to listen anyway.
== keepcb.teddy
The teddy from {kmap} has been given to {B}, who denies caring and sleeps with a hand on its ear.
== keepcb.seeds
{A} planted the seeds from {kplace} in a boot box on the sill, checks it twice a day, and says it is fine. Nothing has come up yet.
== keepcb.cards
They play with the deck from {kplace} now, minus the seven of clubs, which {A} replaced by cutting a new one from a ration box and has never been caught.
== keepcb.harmonica
The harmonica from {kplace} wanders around {camp} from hand to hand; {A} is the only one who can get a real tune out of it, and only when no one is looking.
== inj.title
{A} is still favouring {A_his} {site}
{A}'s {site} has not forgotten {kmap}
How {A} is getting on
{A} will not admit it still hurts
== inj.fresh
{A} came back from {kmap} on day {kd} with {A_his} {site} bound in {cloth}; {A_he} insists it is nothing and puts no weight on it.
== inj.mid
{A}'s {site} is still bound; the wrapping has gone grey, and {A_he} does the one-handed jobs and swears at the two-handed ones.
{A} cannot {job} with a bad {site}, so {A} has been given the job of watching the others do it, which is worse.
The wound {A} took at {kmap} {kd_ago} still weeps in the mornings, and {A} wraps it with {cloth} before anyone is up.
== inj.healed
{A} took the wrapping off today. The {site} is a pale new thing, puckered and hairless, and everybody was invited to look.
The {site} has closed over into a scar from {kmap}, and {A} traces it when {A_he} thinks no one is looking.
== scar.cb
{A}'s scar from {kmap} goes white in the cold, and {A} knows the weather by it.
== grief.title
{A} is still setting two bowls
{D} has been gone {dgo}
{A} cannot stop looking at {D}'s bunk
{A} walks the wall for {D}
== grief.line
The bunk is made tight, with the corners square, and {A} will let no one sit on it.
{A} found {dpos} belonging to {D} in a coat pocket, held it, and did not say anything for a long time.
{A} still catches {A_himself} turning at the door to say something to {D}.
{A} walked the wall at night for a week and nobody asked why, or tried to stop {A_him}.
{A} cannot eat the soup {D} used to make, and cannot throw it out either.
== death.title
{D} is gone
We buried {D} by {kplace}
{A} washed {D}'s hands
{A} sat up with {D}
== death.line
{D} died with {D_his} {dsite} still bandaged in {dcloth}, grey with a week of wearing.
{A} sat up with the body, because it seemed wrong for it to lie alone, and told it all the small ordinary things there had not been time for.
{A} wrapped {D} in a blanket and tied it with cord, tight, and the cord bit into the wool, which smelled of {D}.
The kids were told, and some of them understood.
{D}'s {dposx} went to {B}, who has put it where the light falls.
{D}'s place at the table stayed empty, and nobody set a bowl, and then {A} set one.
== death.rel
{D} had been teaching {C} to read the wind off a scrap of cloth; {C} tied the scrap to the cross.
{C} had hardly left {D}'s side for a month, and walked back from the grave alone.
== prep.title
{A} is laying out the next raid on the table
Before the next raid, {A} checks the gear
{A} mapped the next push in flour
{A} will not say where, only that it will not be quiet
== prep.event
{A} chalked {map} on the table, {place} in one corner and {place2} in the other, and gave {enemies} three black stones at the door.
{A} went over {map} again with a stick in the dirt: in through {place}, out through {place2}, and a spot behind the stairs where a person could lie low for an hour.
{A} says {enemies} will take {place} if the lines go the way they went last time, and wants a rifle there before dusk.
== prep.stock
There are {ammo_n} in the tin and {food_n} in the cupboard; {A} writes both on the wall with chalk as if daring them to go lower.
{A} issued the {item_pl} from {kplace} for the next push: {n} to the front, the rest locked away.
== prep.away
With {AW} still out there, nobody wants to say what the odds are, so {A} says nothing and checks the straps twice.
{A} keeps the lamp lit in the window for {AW} and trims the wick every hour.
== prep.recent
After {prev_map} yesterday ({prev_res}), {A} wants one more go at the same ground.
After {prev_map} yesterday ({prev_res}), {A} wants it done differently this time.
== rel.title
{A} and {B}
Between {A} and {B}
Something about {A} and {B}
{A}, {B}, and a small thing everyone noticed
== rel.rival.1
{A} and {B} had a bet about who would carry the heavier sack out of {map}; {A} lost and paid in pickled onions.
== rel.rival.2
{A} and {B} did not speak at supper. It was over a spoon again, or the idea of one, and the bench went quiet around them.
== rel.rival.3
{B} stood between {A} and the door and said everything that had waited a year. {A} listened to all of it, nodded, said fine, and went out; it is as close as they have come to an apology.
== rel.rival.4
{A} and {B} were seen carrying one water barrel between them, one at each handle, not looking at each other. The bench has put money on a truce.
== rel.sweet.1
{A} and {B} drew the same watch again, and traded the good post back and forth until one of them gave in.
== rel.sweet.2
{A} found a wildflower in a tin cup on the shelf above {A_his} bunk and has told no one who put it there. {B} has been very busy.
== rel.sweet.3
{A} and {B} stood too close at the stove, shoulder to shoulder, not touching, for the whole time it took the soup to boil.
== rel.sweet.4
{A} and {B} were seen going out the back door together before dawn, one hand on a lamp and one hand on each other's sleeve. {camp} pretends it noticed nothing and talks of little else.
== rel.mentor.1
{B} sat with {A} behind the wall and taught {A_him} to read the wind from a scrap of cloth.
== rel.mentor.2
{A} fixed a strap that {B} had shown {A_him} how to fix a month ago, and {B} pretended to be surprised.
== rel.mentor.3
{B} handed {A} the better knife, handle first, and did not say why.
== rel.mentor.4
{A} corrected {B} in front of everyone, and {B} said thank you, with {B_his} jaw set, and meant it.
== rel.kin.1
{A} and {B} share a blanket and a nose, and nobody can remember which of them is the elder.
== rel.kin.2
{A} cut {B}'s hair on the porch, and the leavings blew into the vegetable beds.
== rel.kin.3
{B} carried the whole bucket up the stairs so {A} would not have to; {A} let {B}, and said thank you without being asked.
== rel.kin.4
{A} lent {B} the good coat for the watch and gave no sign of minding that it came back smelling of someone else's smoke.
== prof.title
{A} and the {poss_short}
What {A} carries
{A} does not like {fear}
Small things about {A}
== prof.poss
{A} keeps {poss} in an inside pocket and touches it when the lamps go low.
{A} has {poss} that nobody has ever been allowed to hold.
{A} lost {poss} for a day and turned {camp} upside down until it was found under a boot.
== prof.fear
{A} is afraid of {fear}, and {A_he} {fear_what}.
{A} has never said so, but {A_he} is afraid of {fear}; {A_he} {fear_what}.
== prof.past
{A} was a {past}, and it shows in the way {A_he} sets the table, or the way {A_he} watches the door.
Before all this {A} was a {past}; {A_he} mentions it only when it is dark.
== prof.calm
{A} listens to everything and answers a third of it, and {camp} has learned to read the other two thirds in {A_his} face.
== prof.hot
{A} threw a boot at the wall over nothing, then picked it up and cleaned it, and everyone agreed to have seen nothing.
== prof.anxious
{A} checks the latch four times and the window twice, and {camp} sleeps better for it.
== prof.dry
{A} said the soup was an acquired taste, and no one has yet acquired it.
== prof.tender
{A} gave away the last of {A_his} bread to a child who did not ask for it, and said {A_he} was not hungry.
== prof.stubborn
{A} refused the advice of three people on how to patch the roof, patched it {A_his} own way, and was proved right in the next rain, and said nothing about it.
== quip.good.calm
"We will manage," {A} said, and for once it sounded like a plan.
"I always did like it when the quiet comes back," {A} said, looking at the stove.
== quip.good.hot
"Next time I come with you," {A} said, thumping the table so the cups danced.
== quip.good.anxious
"It won't last," {A} muttered, and went to check the latch anyway.
== quip.good.dry
"A thousand years of peace, then," {A} said, dry as bone. "Until Thursday."
== quip.good.tender
"Come and eat, you've earned it," {A} said, and the voice was softer than the words.
== quip.good.stubborn
"I said it would hold," {A} said, to nobody in particular.
== quip.bad.calm
"One bad day is not a bad life," {A} said, and meant it, as far as anyone could tell.
== quip.bad.hot
"If I'd been there," {A} said, and did not finish, and did not need to.
== quip.bad.anxious
"What if they come here next?" {A} asked, and nobody wanted to answer.
== quip.bad.dry
"Well," {A} said, "that went about as well as the last one."
== quip.bad.tender
"Sit," {A} said, "sit, eat, it will keep," and pushed a bowl across the table.
== quip.bad.stubborn
"We go back," {A} said. "We go back, and we do not lose twice."
"""
