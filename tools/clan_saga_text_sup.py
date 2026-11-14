"""Clan saga text for the supplies per category (tools/clan_supply.py): the scene of a hungry or sick member whose trouble the memory ties to the day's shortage.  English only.
Variables: {lack_n} (the missing units, "three units"), {lack_days} (days the larder of that kind still lasts, "no days" / "one day"), {stock_n} (units left in the larder)."""
TEXT = r"""
== inj.title
{A} and the {site} that will not mend
Still limping home from {kmap}
{A} keeps testing the {site}
The {site} again
{A} is not as well as {A_he} says
A scar in the making on {A_his} {site}
{A}'s {site}, a week on
Bandages and {A}
== rel.title
{A} and {B}, after supper
Between {A} and {B}, again
What {A} and {B} are not saying
Notes on {A} and {B}
{A} and {B}, side by side
Something in the way {A} and {B} sit
The two at the end of the table
{B}, and {A} noticing
== win.hs
{hs_p}, and {A} swears the room went quiet for each one.
{hs_p} from the line, and {A} wants every one of them drawn on the wall.
{hs_p}, and {A} has started to hold out {A_his} hands as if to feel the recoil secondhand.
{hs_p}, and nobody argued with how you told it.
{hs_p}, and {A} says the old men would have called it luck, and then crossed themselves.
== lack.title
{A} went without
The larder ran dry
Short again
Not enough on the table
{A} gave up the last of it
What the day did not bring
== lack.food
The cans ran out before {A} was served, and the pot was scraped twice for what was left.
{A} chewed a strip of dried rind to the end and called it supper. The sack held {lack_n} less than the camp ate.
{A} went to bed hungry, and the whole room heard it. The day fell {lack_n} short of food.
Nobody had the nerve to count the empty plates. {A}'s was one of them.
{A} divided one can of beans four ways and took the smallest share, with the larder at {lack_days} of food.
The kitchen was swept bare. {A} licked the spoon and set it down without a word.
{A} pushed the bowl toward {B} and said already ate, which nobody believed.
== lack.water
The barrels went down fast, and by dusk {A} was sharing a cup with {B}.
{A} boiled the same pot of water twice. The camp was {lack_n} short on water, and everybody knew it.
{A}'s lips were cracked by evening, and the water ration did not stretch to a second cup.
Water was counted by the mouthful. {A} wet a rag and held it to {A_his} neck instead of drinking.
The filter dripped all night, and by morning {A} was first in line with an empty bottle.
With {lack_days} of water in the barrels, {A} stopped washing and started saving.
== lack.med
The last bandage went on someone else, and {A} lay still and did not ask for it.
{A} shivered under two coats. The medicine shelf was {lack_n} short of what the sick need, and the camp knows what that means.
There was nothing for the fever but cold cloths. {A} said {A_his} head would clear by morning, and it did not.
{A} counted the pills in the tin twice. They did not add up to a night's dose for everyone who needed one.
The antibiotics ran out on {A}'s turn, and {B} sat up with {A} instead.
With {lack_days} of medicine on the shelf, {A} watched the tin the way other people watch a door.
== lack.tail
The shortage is on the board by the door in chalk, and nobody wipes it.
The next raid has to bring it back, or this will happen again.
It is in everyone's face, even when no one says it.
{B} said it will not last, and kept looking at the pot.
Somebody wrote it in the book, as if writing it down would fill the shelf.
== haul.finds
The details were told over the open sack. {finds_text}
Everyone wanted the story of each piece. {finds_text}
The list does not say how it was found. {finds_text}
Some of it came with a story. {finds_text}
{A} read the finds out like a verse. {finds_text}
Nothing came home without a place to remember it by. {finds_text}
The count hides the small things. {finds_text}
{B} wrote each piece down with the spot where it was found. {finds_text}
== keepfind.title
The {kfind} from {kmap}
What {A} did with the find from {kmap}
A find from day {kd}
The small thing from {kmap}
== keepfind.line
The find from {kmap} (day {kd}), the {kfind}, has not left {A}'s pocket since. The kids ask about it, and {A} tells it differently every time.
{A} wiped the find from {kmap} ({kfind}) with a wet thumb and set it where the lamp hits it. It belongs to nobody and to everyone.
Somebody asked where the {kfind} came from. {A} said {kmap}, day {kd}, and then told the whole story, including the parts that did not happen.
The find from day {kd}, the {kfind}, sits on the shelf by the door. {B} touches it on the way out, every time, for luck.
Nobody needed the {kfind} from {kmap}. That is exactly why {A} would not trade it.
{A} gave up a day's soup to see the find ({kfind}) and called it the best price the camp ever paid.
== dep.title
{A} stopped talking at the table
{A} and the long silence
Nobody could reach {A}
{A} and the empty hours
== dep.line
{A} has stopped coming to the fire. The food is on the plate when {B} brings it, and it is still on the plate when {B} comes back.
For days {A} has said nothing that was not an answer. {B} sits close and does not ask, which is all anyone can do.
{A} stares at the wall where the day's tally is chalked. The numbers have not gone up in a long time, and {A} has stopped pretending they will.
Somebody found {A} sitting in the dark with the lamp unlit. Nobody said anything; {B} just sat down on the other side of the door.
{A} folded the blanket, unfolded it, folded it again. It is the only thing in the camp that {A} still manages to finish.
The camp is thin and the shelves are thinner, and {A} has gone somewhere none of them can follow. A good raid might bring {A} back.
== dep.up
{A} ate a whole bowl today and asked for the salt. {B} looked away so nobody would see the smile.
The raid helped. {A} came to the fire and held out both hands to it, and for the first time in days said a full sentence.
{A} is mending: a little speech, a little soup. {B} keeps watch without making it look like watch.
"""
