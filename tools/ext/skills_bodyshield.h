// skills.c SK[] row of the BODYSHIELD skill, included only with -DT2R_BODYSHIELD=1 (skills.h). Kept out of skills.c's own text so the
// launcher / widget generators that read skills.c (gen-gamedata.py, gearup13_widgets.py, ...) see the public build's 32 skills.
    // a bodyshield perk, more expensive than other perks, with tiers (bodyshield.c / bodyshield.h, re/bodyshield-1117.md)
    [SK_BODYSHIELD] = {"BODYSHIELD", SK_ICON("bodyshield"), 3, {4, 6, 8}, 7,
        {"Press |gen:interact| behind or beside an enemy to grab them. Choke them out, or aim to hold them as a human shield. Break free: 2.5 s of mashing.",
         "Grab an enemy, choke them out or hold them as a human shield. Breaking free takes longer: 3 s of mashing.",
         "Grab an enemy, choke them out or hold them as a human shield. Breaking free takes even longer: 3.5 s of mashing."},
        "No 2013 skill. The victim gets one escape prompt while the kill is blocked (the first ~1.7 s); aiming turns them into a shield their own team can shoot, mashing F frees them (2.5 / 3 / 3.5 s at the cap, 9.25 / 11.1 / 13 s without a press), stopping the aim or taking any damage lets them go. Iron Grip counts against it."},
