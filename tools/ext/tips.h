// tools/ext/tips.h - the ONE tip list
// . 29 tips from the old 16 loading tips (MF_TIPS) + 33 death tips (DU_TIPS, 40 different lines). The loading screen shows "CAT:" + the
// text and steps to the next tip every 7 s; the death screen shows the text on its SP illustration (streaming/large/death-tips/<img>.png, the pictures
// the old death list used; suppressor / mark / listen / headshot had none and take the closest unused one). Polish: tools/loc/pl/04-matchflow.txt.
// Keep tools/features/matchflow_widgets.py TIPS in step (its first tip is the loading widget's placeholder).
#ifndef T2R_TIPS_H
#define T2R_TIPS_H
// npic: the loading screen's framed box shows the tip's own screenshot, streaming/t2r/clan/tip-<NN>-<1..npic>.png
// (tools/models/figures/tips_ship.py, re/tips-1118/src; the CLAN tip rotates its 3 generic shots).
static const struct { const char *cat, *text, *img; int npic; } T2R_TIPS[] = {
    {"WEAPONS", "The Molotov flushes enemies out of cover. Arc-throw it from low cover to stay hidden while you throw.", "use-molotov", 1},
    {"WEAPONS", "Shotguns are deadly up close but fall off fast. Keep moving and close the distance.", "weapon-shotgun", 1},
    {"WEAPONS", "A suppressor keeps your shots quiet. Pick your fights.", "crouch-beside-enemy", 1},
    {"WEAPONS", "The bow is silent, and a fully drawn arrow hits harder. Pick your arrows back up after the fight.", "silent-bow", 1},
    {"WEAPONS", "Bullets drop with gravity. Aim higher to compensate.", "weapon-bullet-drop", 1},
    {"WEAPONS", "A pipe bomb's fuse burns for a moment before it goes off. Lob one over cover to catch an enemy hiding behind it.", "use-pipe-bombs", 1},
    {"WEAPONS", "Smoke bomb clouds completely block enemy vision, hiding your movements and preventing them from firing on you.", "player-upgrade-stun-bomb-smoke", 1},
    {"WEAPONS", "One-handed melee weapons are fast and durable. Two-handed melee weapons are slower but deal massive damage.", "melee-weapon-types", 1},
    {"WEAPONS", "Upgraded melee weapons are restored to full durability and have greatly increased damage.", "upgraded-melee", 1},
    {"SURVIVAL", "Crafting takes time. Make medkits and bombs before the fight, not during it.", "ellie-in-backpack", 1},
    {"SURVIVAL", "Healing takes time. Run from the fight and use your health kit somewhere safe.", "use-health-kit", 1},
    {"SURVIVAL", "Supply boxes refill over time. Remember where they are.", "scavenge-items", 1},
    {"SURVIVAL", "Armor soaks up damage from every direction. Buy it early.", "shooting-armor-legs", 1},
    {"TEAMWORK", "A downed teammate can be revived. Mark them and run to them - the run doesn't drain your stamina.", "buddy-rescue", 1},   // helpcall.c hc_rush_towards
    {"TEAMWORK", "Mark an enemy to show your whole team where they are.", "general-flank-them", 1},
    {"TEAMWORK", "Stick together. A lone survivor is easy prey for the other faction.", "overwhelmed", 1},
    {"STEALTH", "Stay low in the grass. A prone survivor is hard to spot.", "grass-crouch-prone", 1},
    {"STEALTH", "Listen mode shows you footsteps. Moving slowly keeps you off it.", "escape-sneak", 1},
    {"STEALTH", "Use the environment to lose your enemies. They will search your last known position, so don't be there.", "hide", 1},
    {"STEALTH", "Breaking glass windows can open up new routes, but the sound will draw enemy attention.", "glass-break", 1},
    {"COMBAT", "Enemies are deadly accurate when you charge straight at them. Use the environment to flank them instead.", "easy-target", 1},
    {"COMBAT", "Enemies are less accurate while you're sprinting away or to the side.", "sprint-to-avoid", 1},
    {"COMBAT", "Stay crouched behind cover to protect yourself from gunfire.", "cover-from-gunfire", 1},
    {"COMBAT", "Look around to track enemy movements so you aren't caught off guard.", "general-dont-get-flanked", 1},
    {"COMBAT", "Stand still to steady your aim. Crouching makes you more accurate, and going prone even more.", "stand-aim-rifle", 1},
    {"COMBAT", "Headshots down enemies faster. Take your time and aim.", "crouch-prone-aim", 1},
    {"COMBAT", "Finishing a downed enemy earns more parts. Watch for their friends.", "vulnerable-enemies-5-6", 1},
    {"COMBAT", "If your usual plan isn't working, vary your tactics: fight quietly, by force, or avoid the fight. Try a new weapon or crafting recipe.", "general-vary-your-tactics", 1},
    {"CLAN", "Parts you earn in a match become supplies for your clan. Every survivor eats, so keep them fed.", "limited-supplies", 3},
};
#define T2R_NTIPS (int)(sizeof T2R_TIPS / sizeof T2R_TIPS[0])
#endif
