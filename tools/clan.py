"""2013 Factions clan (the 12 weeks) - server side rules + storage. Imported by daemon.py.

The numbers and the order of the steps are the PS4 Remastered v1.11 engine's (EBOOT ProcessClanDay 0x397620 + ProcessEvent 0x398bc0 +
CheckStartEvent 0x39c0e0 + StartNewEvent 0x39b230, the *clan-vars* / *clan-events* / *firefly-story-events* / *net-missions* data of
net-10.bin); the full decode with addresses is re/factions2013/ps4/logic/clan.md. In short:
  needed per day   = 5 + 2N - floor(1.2N)                  (N = healthy + hungry + sick; the HUD shows exactly this integer)
  supplies         = bottles + floor(parts * 0.02)         (x late-join multiplier), nothing is banked (the carry-over cap *clan-vars*[+8] is 0)
  surplus / deficit = trunc(supplies - needed)
  deficit day      : healthy -> hungry floor(0.75 d) (deterministic), then a random member (ANY alive one: a pick on somebody already sick
                     is wasted and costs one more death) falls sick |0.3 d| times (no new sick when 90 %+ of a clan of 5+ is sick),
                     then deaths = ceil(0.2 * sick at the day's start + wasted picks), more than 12 -> 10; the dead are picked sick first,
                     then hungry, then healthy
  surplus day      : heal hungry 0.35 s, heal sick max(1, 0.3 s), then 0.1 s new (healthy) survivors; fractions are rolled
                     (floor(x) + one more with probability frac(x)), nothing dies
  the sickness of a member is separate from its hunger: somebody can be sick AND hungry (shown as sick; the hunger comes back when the
  sickness is cured). The hidden count of those lives in meta["sh"].
  events           : the calendar below. An event starts on its day, lasts THREE matches and is settled by the mission played in those
                     matches (the mission's tier goals, see MISSIONS): growth events add ceil(size * 0 / 5 / 7 / 10 %) survivors, attacks
                     kill ceil(size * 60/40/20/10 % early, 100/60/40/20 % late) of the clan after that day's supplies (sick first).
                     Tier 1..3 also pays one-use boosters (BOOSTER_ROWS). Nothing else pays survivors: no mission outside an event does.
                     During an attack event (its three matches) the player earns ATTACK_PARTS_BONUS (10 %) more parts (missions.md); the ext books it
                     as an "Attack Bonus" award row at award time, so the HUD, the scoreboard and the day's parts all include it.
  a match not played to its end: the player's clan day is processed with 0 supplies (the leave path calls ProcessClanDay(0, 0)); an
                     idle player (0 parts) gets a 2.0 time multiplier, and a day whose multiplier is above 1.6 does not count as a day
  12 weeks         : the clan wins when 83 days are done (the last story entry, day 83 = "clan won"); one match = one day, start = 5 healthy.
State is keyed by the player's token id = token bytes 20..31 (the 12-byte install id T2R-Play.ps1 puts behind the name), so a rename
keeps the clan.
"""
import json, math, random, struct, time, zlib
import clan_supply

WEEKS = 12
DAYS = WEEKS * 7                  # 84: the display runs W12 D7, but the clan has won once 83 days are done (WIN_DAY)
WIN_DAY = 83                      # *firefly-story-events* entry 7 (trigger 83, "clan won"); ProcessClanDay 0x397620 sets the won flag at day >= 83
START_SURVIVORS = 5               # *clan-vars* +0x04
MAX_CLAN = 512                    # member slots of the engine (0xa38 count, < 0x200)
PARTS_PER_SUPPLY = 50             # *clan-vars* +0x20 = 0.02 supplies per part (ProcessClanDay: trunc(parts * 0.02))
NONE, WLF, SERAPHITES = 0, 1, 2   # WLF replaces the Fireflies, Seraphites the Hunters
FACTION_NAMES = {NONE: "", WLF: "WLF", SERAPHITES: "SERAPHITES"}
ALIVE, DEAD, WON = 1, 2, 3        # status; 0 = no clan yet (first launch: CHOOSE YOUR SIDE)

# ------------------------------------------------------------------ the day (ProcessClanDay 0x397620)
HUNGRY_PER_DEFICIT = 0.75         # *clan-vars* +0x68 lambda 0x8a28: healthy -> hungry, int() of it (no roll)
SICK_PER_DEFICIT = 0.3            # +0x78 lambda 0x20fa8: |0.3 * deficit|, rolled
SPIRAL_SICK_SHARE = 0.9           # ... and 0 when the clan is 5+ strong and this share of it is already sick
DEATH_PER_SICK = 0.2              # +0x70 lambda 0x23878: ceiling(0.2 * sick + 1.0 * wasted sick picks)
DEATH_CLAMP_OVER, DEATH_CLAMP_TO = 12, 10
HEAL_HUNGRY_PER_SURPLUS = 0.35    # +0x90 lambda 0x48ef0, rolled
HEAL_SICK_PER_SURPLUS = 0.3       # +0x88 lambda 0x23850: 0.3 s when > 1, else 1 (surplus > 0), rolled
GROW_PER_SURPLUS = 0.1            # +0x80 lambda 0x1e998, rolled
DAY_MULT_LIMIT = 1.6              # a day only counts (day counter, mission and event clocks) when the multipliers' product is <= 1.6
IDLE_MULT = 2.0                   # the post-match handler sets 2.0 for a player with no score, no supply bottle and no death
# ------------------------------------------------------------------ events (CheckStartEvent 0x39c0e0, story tables)
EVENT_LEN = 3                     # *clan-vars* +0x48: an event's mission runs three matches (days start .. start + 2)
ATTACK_EARLY = (-0.6, -0.4, -0.2, -0.1)       # *firefly-story-events* / *hunter-story-events* entries 0, 1: tier 0 / 1 / 2 / 3 casualties
ATTACK = (-1.0, -0.6, -0.4, -0.2)             # entries 2 .. 6
# missions.md (and the wiki table) say 5 / 7 / 10 %; the game data (*clan-events*) decodes tier 2 as 7.5 %. The doc wins: 7 %.
GROWTH = (0.0, 0.05, 0.07, 0.10)              # *clan-events* entries 1 .. 7 (all "new members" type)
ATTACK_PARTS_BONUS = 0.10                     # missions.md: "during this event [the attack] the player gains 10% more Parts" (ext award_hook, "Attack Bonus")
# start day of every event: the story attacks are fixed (entry +0x48); a random growth event starts once the event is over, the 2 quiet
# days (*clan-vars* +0x4c / +0x50 = 2) have passed, the clan is past day 4 (+0x54) and the next story event is more than 4 days away
EVENT_DAYS = {d: ("growth", GROWTH) for d in range(5, 81, 5)}
EVENT_DAYS.update({15: ("attack", ATTACK_EARLY), 30: ("attack", ATTACK_EARLY), 35: ("attack", ATTACK),
                   50: ("attack", ATTACK), 65: ("attack", ATTACK), 75: ("attack", ATTACK), 80: ("attack", ATTACK)})
# the five growth events of missions.md, by (day // 5) % 5; the client (t2r-ext.c ev_fill GN / GR) shows the name and the description with the enemy
# faction of the clan (WLF replaces the Fireflies, Seraphites the Hunters). Marauder Attack is a growth event in the doc (repel them -> survivors join).
GROWTH_NAMES = ("FRIENDLY SURVIVORS", "DYSENTERY OUTBREAK", "MALARIA OUTBREAK", "RESCUE ALLIES", "MARAUDER ATTACK")
EV_NONE, EV_GROWTH, EV_ATTACK = 0, 1, 2
rng = random.Random()             # tests replace it


def f32(x):
    """Round to float32 like the engine's lambdas do."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def event_today(day):
    """(kind, name id) of the event STARTING on day index `day` (the day about to be played); (0, 0) = none. Deterministic,
    so the menu can announce it before the match."""
    e = EVENT_DAYS.get(day)
    if not e:
        return EV_NONE, 0
    return (EV_GROWTH, (day // 5) % len(GROWTH_NAMES)) if e[0] == "growth" else (EV_ATTACK, 0)


def event_window(day):
    """Start day of the event whose three matches contain day index `day`, or -1."""
    for s in range(day, max(-1, day - EVENT_LEN), -1):
        if s in EVENT_DAYS:
            return s
    return -1


def rnd(x):
    """Half up (survivors are whole people)."""
    return int(math.floor(x + 0.5))


def roll(x):
    """The engine's fractional loop: floor(x) always, one more with probability frac(x) (x <= 0: nothing)."""
    if x <= 0:
        return 0
    n = int(x)
    if rng.random() < x - n:
        n += 1
    return n


def token_id(token):
    """12-byte install id = token bytes 20..31 (hex chars 40..63); whole token if not 64 hex."""
    t = (token or "").lower()
    return t[40:64] if len(t) == 64 else t


def needed(n):
    """Supplies needed per day for a clan of n: lambda 0x2c000 (5 + 2n) minus lambda 0x30a50 (1.2n), both cut to int
    (FUN_003956d0 / FUN_00395830 cast the lambda results): 5 + 2n - floor(1.2n) = 5 + ceil(0.8n). 5 -> 9, 25 -> 25, 38 -> 36 (HUD 21/36)."""
    return 5 + 2 * n - (6 * n) // 5 if n > 0 else 0


def supplies_of(parts, bottles=0):
    """Whole supplies of a match: supply bottles + trunc(parts * 0.02f)."""
    return max(0, int(bottles)) + int(f32(max(0, int(parts)) * f32(0.02)))


def week_day(day):
    """day = days done (0..84) -> (week, day of week) of the day being played, 1-based."""
    d = min(day, DAYS - 1)
    return d // 7 + 1, d % 7 + 1


def new_clan(faction):
    return {"faction": faction, "status": ALIVE, "day": 0,
            "healthy": START_SURVIVORS, "hungry": 0, "sick": 0, "boost_hi": START_SURVIVORS // BOOSTER_EVERY}


# ------------------------------------------------------------------ the members (healthy / hungry / sick / sick AND hungry)
class Crowd:
    """The clan as four counts. The engine keeps one flag set per member (dead / sick / hungry); a member can be sick and hungry at once,
    and the clan screen shows it as sick. h = neither, u = hungry only, s = sick only, su = both."""
    def __init__(self, h, hu, s, sh=0):
        sh = max(0, min(int(sh), s))
        self.h, self.u, self.s, self.su = h, hu, s - sh, sh

    @property
    def size(self): return self.h + self.u + self.s + self.su
    @property
    def hungry_shown(self): return self.u
    @property
    def sick_shown(self): return self.s + self.su

    def pick(self, weights):
        """Uniform pick among the members of the given categories (a list of (name, count)); returns the name or None."""
        tot = sum(c for _, c in weights)
        if tot <= 0:
            return None
        k = rng.randrange(tot)
        for name, c in weights:
            if k < c:
                return name
            k -= c
        return None

    def make_hungry(self):                 # FUN_00395990: random among alive members that are not hungry
        w = self.pick((("h", self.h), ("s", self.s)))
        if w == "h": self.h -= 1; self.u += 1
        elif w == "s": self.s -= 1; self.su += 1
        return w is not None

    def make_sick(self):                   # FUN_00395b30(1): random among ALL alive members; a pick on a sick one changes nothing (wasted)
        w = self.pick((("h", self.h), ("u", self.u), ("s", self.s), ("su", self.su)))
        if w == "h": self.h -= 1; self.s += 1; return 1
        if w == "u": self.u -= 1; self.su += 1; return 1
        return -1 if w else 0              # -1: a sick member was picked

    def heal_hungry(self):                 # FUN_00395d70: random hungry member
        w = self.pick((("u", self.u), ("su", self.su)))
        if w == "u": self.u -= 1; self.h += 1
        elif w == "su": self.su -= 1; self.s += 1
        return w is not None

    def heal_sick(self):                   # FUN_00395ef0: random sick member
        w = self.pick((("s", self.s), ("su", self.su)))
        if w == "s": self.s -= 1; self.h += 1
        elif w == "su": self.su -= 1; self.u += 1
        return w is not None

    def kill(self):                        # FUN_00396070: a random sick member, else a hungry one, else any
        if self.s + self.su:
            w = self.pick((("s", self.s), ("su", self.su)))
        elif self.u:
            w = "u"
        else:
            w = "h" if self.h else None
        if w:
            setattr(self, w, getattr(self, w) - 1)
        return w is not None

    def add(self, n=1):                    # FUN_00396410: new members are healthy (512 slots at most)
        n = min(n, MAX_CLAN - self.size)
        self.h += max(0, n)
        return max(0, n)


def resolve_day(clan, parts, left_early=False, downs=0, counts=None, mult=1.0, forgive=False, bottles=0):
    """One match = one day (ProcessClanDay). Returns (new clan dict, result dict). Pure except for rng.
    downs / counts: the match's mission counts ({mission id: n}, downs = counts[1]); mult = the late-join multiplier of the match
    (supplies x mult, a day above 1.6 does not count); forgive = a late joiner: a deficit is forgiven (the engine tops the multiplier up)."""
    c = dict(clan)
    counts = dict(counts or {})
    if downs and 1 not in counts:
        counts[1] = int(downs)
    meta = meta_of(c)
    cr = Crowd(c["healthy"], c["hungry"], c["sick"], meta.get("sh", 0))
    n = cr.size
    sick0 = cr.sick_shown
    need = needed(n)
    parts = max(0, int(parts))
    idle = (not left_early) and parts == 0 and bottles <= 0
    sup = 0 if left_early else supplies_of(parts, bottles)       # a left match: ProcessClanDay(0, 0)
    mult_all = float(mult) * (IDLE_MULT if idle else 1.0)
    eff = f32(mult * sup)
    q = int(eff - need)                                            # trunc toward zero, as the engine's (int)
    deficit, surplus = max(0, -q), max(0, q)
    if forgive and deficit > 0:
        deficit = 0
    counted = mult_all <= DAY_MULT_LIMIT
    r = {"day": c["day"], "parts": parts, "supplies": int(eff), "needed": need, "left": int(bool(left_early)),
         "died": 0, "new_hungry": 0, "new_sick": 0, "healed": 0, "gained": 0, "counted": int(counted)}
    if n <= 0:
        return c, r
    if deficit > 0:
        # healthy -> hungry: int(0.75 d), no roll
        for _ in range(int(f32(f32(HUNGRY_PER_DEFICIT) * deficit))):
            if cr.make_hungry():
                r["new_hungry"] += 1
        # hungry -> sick: |0.3 d| rolled; any alive member can be picked, a sick one is wasted and costs a death later
        spiral = n > 4 and f32(sick0 / n) >= f32(SPIRAL_SICK_SHARE)
        wasted = 0
        for _ in range(0 if spiral else roll(f32(f32(SICK_PER_DEFICIT) * deficit))):
            k = cr.make_sick()
            if k > 0: r["new_sick"] += 1
            elif k < 0: wasted += 1
        # deaths: ceiling(0.2 * sick at the day's start + wasted), more than 12 -> 10
        d = int(math.ceil(f32(f32(f32(DEATH_PER_SICK) * sick0) + wasted)))
        if d > DEATH_CLAMP_OVER:
            d = DEATH_CLAMP_TO
        for _ in range(d):
            if cr.kill():
                r["died"] += 1
    elif surplus > 0:
        for _ in range(roll(f32(f32(HEAL_HUNGRY_PER_SURPLUS) * surplus))):
            if cr.heal_hungry(): r["healed"] += 1
        hs = f32(f32(HEAL_SICK_PER_SURPLUS) * surplus)
        for _ in range(roll(hs if hs > 1 else 1.0)):
            if cr.heal_sick(): r["healed"] += 1
        r["gained"] = cr.add(roll(f32(f32(GROW_PER_SURPLUS) * surplus)))
    r.update(evk=0, evn=0, evl=0, evg=0, evt=0)
    day = c["day"]
    if counted:
        day += 1
        _event_step(c, cr, meta, r, counts, left_early)      # mission progress, event result (uses the clan size after the day)
    else:
        _progress_only(meta, r, counts)
    c.update(healthy=cr.h, hungry=cr.u, sick=cr.s + cr.su, day=day)
    if cr.su:
        meta["sh"] = cr.su
    else:
        meta.pop("sh", None)
    c["meta"] = json.dumps(meta, separators=(",", ":"))
    if cr.size <= 0:
        c["status"] = DEAD
    elif day >= WIN_DAY:
        c["status"] = WON
    r["status"] = c["status"]
    return c, r


def _progress_only(meta, r, counts):
    """A match that does not count as a day still counts toward the running mission (+0x1bcc is booked before the day is processed)."""
    m = meta.get("m")
    if m:
        m["prog"] += max(0, int(counts.get(m["id"], 0)))
        r.update(mi=m["id"], mp=m["prog"], ml=m.get("left", 0), mt=0, ms=0, mb=0, mboosters=[], mz=m.get("sz", 0))


def _event_step(c, cr, meta, r, counts, left_early):
    """ProcessEvent (0x398bc0), run on the day the counter was just raised: the running mission gets this match's progress; the event
    whose third match this was is settled by the mission's tier; a practice mission (no event) just runs its three matches."""
    day = c["day"]                                   # the day just played
    m = meta.get("m")
    if m:
        m["prog"] += max(0, int(counts.get(m["id"], 0)))
        m["left"] = max(0, m.get("left", EVENT_LEN) - 1)
    s = event_window(day)
    if m:
        r.update(mi=m["id"], mp=m["prog"], mt=0, ms=0, mb=0, mboosters=[], mz=m.get("sz", 0))
    if s >= 0 and day == s + EVENT_LEN - 1:          # the event's last match: settle it
        kind, pcts = EVENT_DAYS[s]
        tier = 0
        rep = 0
        if m:
            rep = meta.get("rep", {}).get(str(m["id"]), 0)
            tier = sum(1 for g in mission_goals(m["id"], rep) if m["prog"] >= g)
        size = cr.size
        n = int(math.ceil(f32(size * f32(abs(pcts[tier])))))      # float32 like the engine: 25 x 0.6 = 15.0000006 -> 16
        r.update(evk=EV_GROWTH if kind == "growth" else EV_ATTACK, evn=event_today(s)[1], evt=tier)
        if kind == "growth":
            r["evg"] = cr.add(n)
        else:
            lost = 0
            for _ in range(n):
                if cr.kill():
                    lost += 1
            r["evl"] = lost
            r["died"] += lost
        if m:
            nb = BOOSTER_ROWS[min(max(0, rep + tier - 1), len(BOOSTER_ROWS) - 1)] if tier else 0
            r.update(mt=tier, ms=r["evg"], mb=nb, mboosters=[rng.choice(LIVE_BOOSTERS) for _ in range(nb)], mdone=1, ml=0)
            if tier:
                rp = meta.setdefault("rep", {})
                rp[str(m["id"])] = min(9, rp.get(str(m["id"]), 0) + 1)
        meta.pop("m", None)
        return
    if m:
        if m.get("ev", -1) < 0 and m["left"] <= 0:          # a practice mission ends: nothing is paid
            r.update(mt=sum(1 for g in mission_goals(m["id"], meta.get("rep", {}).get(str(m["id"]), 0)) if m["prog"] >= g),
                     mdone=1, ml=0)
            meta.pop("m", None)
        else:
            r["ml"] = m["left"]
    # an event that starts on the next day finds no practice mission in its way (the picker comes back, as in the 2013 flow)
    if meta.get("m") and meta["m"].get("ev", -1) < 0 and (day + 1) in EVENT_DAYS:
        meta.pop("m", None)


# Daily missions (2013 CHOOSE MISSION, *net-missions* of net-10.bin: 38 entries, each with 8 tier goals). id -> (name, award label counted,
# goal list, live). The first three goals are the tiers of a mission never completed; every completed run shifts the three tiers one
# place up the list (GetCurrentMissionGoal 0x3951d0: tier t = list[min(completed + t - 1, 7)]), and a mission that was completed five
# times is greyed out (FUN_0040fe90). Goals do not depend on the clan size. The label is the one t2r-ext's award hook books
# ("Downed Enemy", ...); the ext sends the per-label counts of the match in op 0xE2 (label id = mission id). Not live = no award exists
# yet in the mod (kept so the data model is complete; never offered).
MISSIONS = {1: ("Down Enemies", "Downed Enemy", (3, 6, 9, 15, 20, 25, 35, 45), True),
            2: ("Executions", "Execution", (2, 4, 7, 12, 15, 20, 35, 40), True),
            3: ("Revives", "Revive", (2, 4, 6, 8, 10, 15, 20, 25), True),
            4: ("Headshots", "Headshot", (2, 4, 6, 8, 10, 12, 16, 20), True),
            5: ("Mark Enemies", "Marked Enemy", (7, 14, 21, 28, 35, 42, 48, 56), True),
            # 6..20 (missions.md): counted by the ext (t2r-ext.c mis_book / mis_down_book): 6 one count per two "Heal Teammate" ticks (First-Aid
            # Training), 7 "Special Execution" awards, 8 molotov downs, 9 nail bomb downs, 10 "Gift" awards (Crafter II / III box to a teammate), 11 melee /
            # fist downs, 12 "Shiv Kill" awards, 13 gun / bow downs from 30 m+ (ours: the 2013 data has no distance), 14..20 downs with that exact base gun
            # (9mm = Beretta, Revolver = Taurus, Shorty, Hunting = Remington bolt, Semi Auto = M14, Burst Rifle = rifle-burst, Bow = Ellie's bow).
            # Offered through the same random pool as 40..52 (OFFER_POOL), except 6 which is always on the list.
            6: ("Heal Teammates", "Heal Teammate", (5, 10, 15, 20, 25, 30, 35, 40), True),
            7: ("Special Executions", "Special Execution", (2, 4, 6, 8, 10, 12, 16, 20), True),
            8: ("Down with Molotovs", "Down:molotov", (2, 4, 6, 8, 10, 12, 16, 20), True),
            9: ("Down with Nail Bombs", "Down:nail-bomb", (2, 4, 6, 8, 10, 12, 16, 20), True),
            10: ("Give Crafting Items", "Gift", (2, 4, 6, 8, 10, 12, 16, 20), True),
            11: ("Down with Melee", "Down:melee", (3, 6, 9, 12, 15, 18, 25, 30), True),
            12: ("Shiv Executions", "Shiv Kill", (1, 2, 3, 5, 7, 9, 12, 15), True),
            13: ("Downs from Long Range", "Down:long-range", (2, 4, 6, 8, 10, 16, 20, 24), True),
            14: ("Downs with 9mm Pistol", "Down:pistol-beretta", (3, 6, 9, 15, 20, 25, 35, 45), True),
            15: ("Downs with Revolver", "Down:pistol-revolver-taurus", (3, 6, 9, 15, 20, 25, 35, 45), True),
            16: ("Downs with Shorty", "Down:shotgun-shorty", (3, 6, 9, 15, 20, 25, 35, 45), True),
            17: ("Downs with Hunting Rifle", "Down:rifle-remington-bolt", (3, 6, 9, 15, 20, 25, 35, 45), True),
            18: ("Downs with Semi Auto Rifle", "Down:rifle-m14-semi", (3, 6, 9, 15, 20, 25, 35, 45), True),
            19: ("Downs with Burst Rifle", "Down:rifle-burst", (3, 6, 9, 15, 20, 25, 35, 45), True),
            20: ("Downs with Bow", "Down:bow-ellie", (3, 6, 9, 15, 20, 25, 35, 45), True),
            # Executions with one specific gun: an E execution of a downed enemy (Execution / Special Execution) with that exact base gun in
            # hand (the suppressed variant counts as its base). One mission per primary / secondary gun of the GEAR UP loadouts (not the purchasables); each
            # mission choice offers a random 1-3 of them (EXEC_POOL). Label ids 40.. are what the ext counts (21..24 are the clan saga's extended labels).
            40: ("Variable Rifle Executions", "Execution:rifle-vepr", (2, 3, 5, 7, 9, 12, 15, 20), True),
            41: ("Hunting Rifle Executions", "Execution:rifle-remington-bolt", (1, 2, 3, 5, 7, 9, 12, 15), True),
            42: ("Bow Executions", "Execution:bow-ellie", (1, 2, 3, 5, 7, 9, 12, 15), True),
            43: ("Full-Auto Rifle Executions", "Execution:rifle-mpx5", (2, 4, 6, 8, 10, 12, 16, 20), True),
            44: ("Semi-Auto Rifle Executions", "Execution:rifle-m14-semi", (2, 3, 5, 7, 9, 12, 15, 20), True),
            45: ("Tactical Shotgun Executions", "Execution:shotgun-tactical", (2, 3, 5, 7, 9, 12, 15, 20), True),
            46: ("Frontier Rifle Executions", "Execution:rifle-frontier", (1, 2, 3, 5, 7, 9, 12, 15), True),
            47: ("Burst Rifle Executions", "Execution:rifle-burst", (2, 3, 5, 7, 9, 12, 15, 20), True),
            48: ("9mm Pistol Executions", "Execution:pistol-beretta", (2, 4, 6, 8, 10, 12, 16, 20), True),
            49: ("Revolver Executions", "Execution:pistol-revolver-taurus", (1, 2, 3, 5, 7, 9, 12, 15), True),
            50: ("Burst Pistol Executions", "Execution:pistol-glock", (2, 4, 6, 8, 10, 12, 16, 20), True),
            51: ("Enforcer Executions", "Execution:pistol-cz75-enforcer", (2, 3, 5, 7, 9, 12, 15, 20), True),
            52: ("Shorty Executions", "Execution:shotgun-shorty", (1, 2, 3, 5, 7, 9, 12, 15), True)}
EXEC_POOL = tuple(range(40, 53))    # the gun-execution missions; each mission choice offers a random 1-3 of them (never more)
EXEC_POOL_PICK = (1, 2, 3)
OFFER_POOL = tuple(range(7, 21)) + EXEC_POOL      # the missions a choice offers 1-3 random ones of (beside the always listed 1..6)
MISSION_DAYS = EVENT_LEN          # a practice mission (no event running) also takes three matches
MISSION_REPEAT_MAX = 5            # completions after which the 2013 list greys a mission out (count > 4)
BOOSTER_ROWS = (1, 1, 2, 2, 3, 3, 3, 3, 3, 3)    # *clan-vars* +0xb8 rows: boosters of tier t after r completions = row r + t - 1
ATTACK_GOALS = MISSIONS[1][2][:3]                # (display only) Down Enemies on its first run
TIER_PCT = GROWTH[1:]                            # a growth event pays 5 / 7 / 10 % of the clan (display only)


def mission_goals(mid, repeats=0, size=0):
    """The three tier goals of mission mid after `repeats` completed runs (size is ignored: the goals do not scale with the clan)."""
    g = MISSIONS[mid][2]
    r = max(0, int(repeats))
    return tuple(g[min(r + t, len(g) - 1)] for t in range(3))


def attack_goals(size=0):
    """(display compat) the goals shown on an attack day before a mission is picked: Down Enemies, first run."""
    return mission_goals(1, 0)


def attack_tier(downs, size=0):
    return sum(1 for g in attack_goals() if downs >= g)


def tier_reward(tier, size):
    """(survivors, boosters) a finished event tier (1..3) pays a growth event of a clan of `size`; attacks pay boosters only."""
    if not 1 <= tier <= 3:
        return 0, 0
    return int(math.ceil(f32(size * f32(GROWTH[tier])))), BOOSTER_ROWS[tier - 1]


# ------------------------------------------------------------------ storage
SCHEMA = """CREATE TABLE IF NOT EXISTS clans(
    token_id TEXT PRIMARY KEY, faction INT DEFAULT 0, status INT DEFAULT 0, day INT DEFAULT 0,
    healthy INT DEFAULT 0, hungry INT DEFAULT 0, sick INT DEFAULT 0,
    last_mid TEXT DEFAULT '', last_result TEXT DEFAULT '',
    weeks_total INT DEFAULT 0, runs_won INT DEFAULT 0, runs_lost INT DEFAULT 0, days_total INT DEFAULT 0,
    created REAL, updated REAL)"""
COLS = ("faction", "status", "day", "healthy", "hungry", "sick", "last_mid", "last_result",
        "weeks_total", "runs_won", "runs_lost", "days_total", "boost_hi", "meta")
TEXT_COLS = ("last_mid", "last_result", "meta")
BOOSTER_SCHEMA = """CREATE TABLE IF NOT EXISTS boosters(
    token_id TEXT, bid INT, n INT DEFAULT 0, PRIMARY KEY(token_id, bid))"""


def ensure(c):
    """Create / migrate the clans table on an open sqlite connection (players table untouched)."""
    c.execute(SCHEMA)
    c.execute(BOOSTER_SCHEMA)
    have = {r[1] for r in c.execute("PRAGMA table_info(clans)").fetchall()}
    backfill = "days_total" not in have
    for col, decl in (("last_mid", "TEXT DEFAULT ''"), ("last_result", "TEXT DEFAULT ''"),
                      ("weeks_total", "INT DEFAULT 0"), ("runs_won", "INT DEFAULT 0"),
                      ("runs_lost", "INT DEFAULT 0"), ("boost_hi", "INT DEFAULT 1"), ("meta", "TEXT DEFAULT ''")):
        if col not in have:
            c.execute(f"ALTER TABLE clans ADD COLUMN {col} {decl}")
    if backfill:                                    # saves from before the 2013 rank: lifetime days = whole weeks booked + 1 week per won campaign (the old server booked a win at day 83 = 11 weeks, not 12) + the days of the living clan's current week
        c.execute("ALTER TABLE clans ADD COLUMN days_total INT DEFAULT 0")
        c.execute("UPDATE clans SET days_total = MIN(?, (COALESCE(weeks_total,0) + COALESCE(runs_won,0)) * 7 + CASE WHEN status=? THEN day % 7 ELSE 0 END)", (RANK_MAX_DAYS, ALIVE))


def load(c, tid):
    ensure(c)
    row = c.execute(f"SELECT {','.join(COLS)} FROM clans WHERE token_id=?", (tid,)).fetchone()
    if not row:
        return {"faction": NONE, "status": 0, "day": 0, "healthy": 0, "hungry": 0, "sick": 0,
                "last_mid": "", "last_result": "", "weeks_total": 0, "runs_won": 0, "runs_lost": 0, "days_total": 0, "boost_hi": 1, "meta": ""}
    return dict(zip(COLS, row))


def save(c, tid, clan):
    ensure(c)
    now = time.time()
    vals = [clan.get(k, 0 if k not in TEXT_COLS else "") for k in COLS]
    c.execute(f"INSERT INTO clans(token_id,{','.join(COLS)},created,updated) VALUES(?{',?' * len(COLS)},?,?) "
              f"ON CONFLICT(token_id) DO UPDATE SET {','.join(f'{k}=excluded.{k}' for k in COLS)},"
              "updated=excluded.updated", [tid] + vals + [now, now])


# ------------------------------------------------------------------ 2013 rank (Factions: the symbol next to a PSN id + the weeks survived in total)
RANK_MAX_WEEKS = 999
RANK_MAX_DAYS = RANK_MAX_WEEKS * 7 + 6      # 999 weeks; the cap never lets a day past it
RANK_SYMBOLS = 10                           # the 10 chalk symbols; a 12-week campaign won = one symbol further


def rank_days(total, day_before, day_after, status_after):
    """Lifetime days survived across every clan: + the days this match added; a clan that wins (day 83, the last story entry) books the 84th too
    (12 full weeks). A clan lost / won keeps what it booked; days are never lost."""
    add = max(0, int(day_after) - int(day_before))
    if status_after == WON and day_after >= WIN_DAY:
        add += DAYS - WIN_DAY
    return min(RANK_MAX_DAYS, max(0, int(total or 0)) + add)


def rank_of(clan):
    """(symbol index 0..9, weeks 0..999) of a clan row: the symbol = completed 12-week campaigns (clamped to the 10th), the number = floor(days / 7)."""
    return min(max(0, int(clan.get("runs_won") or 0)), RANK_SYMBOLS - 1), min(RANK_MAX_WEEKS, max(0, int(clan.get("days_total") or 0)) // 7)


def choose_side(c, tid, faction):
    """CHOOSE YOUR SIDE: only when there is no living clan (first launch, clan dead or won)."""
    clan = load(c, tid)
    if faction not in (WLF, SERAPHITES):
        return clan, False
    if clan["status"] == ALIVE:
        return clan, False                      # the choice lasts until the clan dies or wins
    keep = {k: clan[k] for k in ("weeks_total", "runs_won", "runs_lost", "days_total")}
    clan = dict(new_clan(faction), last_mid="", last_result="", **keep)
    save(c, tid, clan)
    return clan, True


# One-use boosters (2013 Factions, Factions_MP.wiki "One-Time boosters"): one is picked on the match flow's
# booster page and is used up when the match starts. Ids 1..7 = the page's rows (t2r-ext MF_BOOSTER);
# 0 = Nothing. LIVE ones have an effect in t2r-ext (feature_boosters); the two firearm-upgrade ones don't
# yet, so they are never handed out.
BOOSTERS = {1: "Starting Ammo Multiplier", 2: "Cheaper Ammo", 3: "Cheaper Armor", 4: "Cheaper Purchased Weapons",
            5: "Starting Small Firearm Upgrade", 6: "Starting Large Firearm Upgrade", 7: "Increased Part Earnings"}
LIVE_BOOSTERS = (1, 2, 3, 4, 7)
BOOSTER_EVERY = 5                 # a booster for every 5 survivors the clan grows to ("+5 NEXT ONE-USE BOOSTER"), the clan-vars +0xc0 table
BOOSTER_MAX = 99


def threshold_booster(k):
    """The booster the clan earns when it first reaches 5 * k survivors: the 2013 table cycles the seven boosters in page order
    (5 -> Starting Ammo, 10 -> Cheaper Ammo, ... 35 -> Increased Parts, 40 -> Starting Ammo again). A booster the mod does not have
    yet is replaced by a live one."""
    bid = (k - 1) % 7 + 1
    return bid if bid in LIVE_BOOSTERS else rng.choice(LIVE_BOOSTERS)


def apply_match(c, tid, mid, parts, left_early=False, counts=None, mult=1.0, forgive=False, bottles=0):
    """End of a match for one player. Once per match id. counts = {award label id: n} of the match (the
    mission's progress). Returns (clan, result or None)."""
    clan = load(c, tid)
    if clan["status"] != ALIVE or not mid or clan.get("last_mid") == mid:
        return clan, None
    new, r = resolve_day(clan, parts, left_early, (counts or {}).get(1, 0), counts, mult, forgive, bottles)
    r["mid"] = mid
    if new["day"] // 7 > clan["day"] // 7:
        new["weeks_total"] = clan.get("weeks_total", 0) + 1   # weeks completed in total (kept; the rank number is days_total // 7)
    new["days_total"] = rank_days(clan.get("days_total", 0), clan["day"], new["day"], new["status"])
    if new["status"] == WON:
        new["runs_won"] = clan.get("runs_won", 0) + 1
    elif new["status"] == DEAD:
        new["runs_lost"] = clan.get("runs_lost", 0) + 1
    new["last_mid"] = mid
    meta = meta_of(new)
    try:                                                    # supplies per category (tools/clan_supply.py): the same engine numbers, split; the stock persists in meta["sup"]
        stock, r["sup"] = clan_supply.book((meta.get("sup") or {}).get("stock"), r["supplies"], r["needed"], clan["healthy"] + clan["hungry"] + clan["sick"],
                                           r["parts"], counts, bool(r.get("left")))
        meta["sup"] = {"stock": stock}
    except Exception:                                       # noqa: BLE001 - a presentation split never breaks the day
        r.pop("sup", None)
    if new["status"] != ALIVE:
        meta.pop("m", None)                                 # clan dead / won: the mission is void
    meta["max"] = max(meta.get("max", 0), clan["healthy"] + clan["hungry"] + clan["sick"],
                      new["healthy"] + new["hungry"] + new["sick"])      # best clan size of this run (end page)
    new["meta"] = json.dumps(meta, separators=(",", ":"))
    # a booster for every BOOSTER_EVERY survivors the clan has grown to (never again for a size it already had)
    size = new["healthy"] + new["hungry"] + new["sick"]
    got = list(r.get("mboosters", []))
    for k in range(clan.get("boost_hi", 0) + 1, size // BOOSTER_EVERY + 1):
        got.append(threshold_booster(k))
    new["boost_hi"] = max(clan.get("boost_hi", 0), size // BOOSTER_EVERY)
    r["boosters"] = got
    new["last_result"] = json.dumps(r, separators=(",", ":"))
    save(c, tid, new)
    for bid in got:
        booster_grant(c, tid, bid)
    return new, r


# ------------------------------------------------------------------ re-booking one match (leave + join in progress back into it)
# A player that leaves a running match and joins it again reports twice for the same match id. Its day must count ONCE, with the
# final result (the stints summed): the rows the first booking changed are kept here, keyed by the match id (persisted: a daemon restart between
# the stints still works), and put back before the final report is booked. The next different match id replaces the snapshot.
SNAP_SCHEMA = "CREATE TABLE IF NOT EXISTS clan_snap(token_id TEXT PRIMARY KEY, mid TEXT, data TEXT, updated REAL)"
SNAP_TABLES = ("clans", "boosters", "clan_story", "clan_feed", "clan_alife")      # every table keyed by token_id that a booking writes


def _has(c, t):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def snap_get(c, tid, mid):
    """The snapshot taken before `mid` was first booked for `tid` (dict) or None."""
    c.execute(SNAP_SCHEMA)
    row = c.execute("SELECT mid, data FROM clan_snap WHERE token_id=?", (tid,)).fetchone()
    if not row or row[0] != mid:
        return None
    try:
        return json.loads(row[1])
    except ValueError:
        return None


def snap_put(c, tid, mid, data):
    c.execute(SNAP_SCHEMA)
    c.execute("INSERT OR REPLACE INTO clan_snap(token_id, mid, data, updated) VALUES(?,?,?,?)", (tid, mid, json.dumps(data, separators=(",", ":")), time.time()))


def snap_take(c, tid, mid, token):
    """Before `mid` is booked for `tid`: keep the rows the booking will change (no-op when this mid already has its snapshot)."""
    if snap_get(c, tid, mid) is not None:
        return
    ensure(c)
    tabs = {}
    for t in SNAP_TABLES:
        if _has(c, t):
            cur = c.execute("SELECT * FROM %s WHERE token_id=?" % t, (tid,))
            tabs[t] = {"cols": [x[0] for x in cur.description], "rows": [list(r) for r in cur.fetchall()]}
    pl = c.execute("SELECT parts_total, parts_n FROM players WHERE token=?", (token,)).fetchone() if _has(c, "players") else None
    snap_put(c, tid, mid, {"tabs": tabs, "players": list(pl) if pl else None, "stint": None, "rejoined": False})


def snap_update(c, tid, mid, **kw):
    s = snap_get(c, tid, mid)
    if s is not None:
        s.update(kw)
        snap_put(c, tid, mid, s)


def snap_restore(c, tid, token, snap):
    """Put the rows back to what they were before the first booking of the match."""
    for t, v in snap["tabs"].items():
        if not _has(c, t):
            continue
        c.execute("DELETE FROM %s WHERE token_id=?" % t, (tid,))
        for r in v["rows"]:
            c.execute("INSERT INTO %s(%s) VALUES(%s)" % (t, ",".join(v["cols"]), ",".join("?" * len(r))), r)
    if snap.get("players") and _has(c, "players"):
        c.execute("UPDATE players SET parts_total=?, parts_n=? WHERE token=?", (snap["players"][0], snap["players"][1], token))


# ------------------------------------------------------------------ missions
def meta_of(clan):
    try:
        m = json.loads(clan.get("meta") or "{}")
    except ValueError:
        m = {}
    return m if isinstance(m, dict) else {}


def mission_choose(c, tid, mid):
    """CHOOSE MISSION: only for a living clan with no mission running. Inside an event's three matches the mission is that event's
    training (its tier settles the event); outside one it is a practice run that pays nothing. Returns (clan, ok)."""
    clan = load(c, tid)
    m = meta_of(clan)
    if clan["status"] != ALIVE or mid not in MISSIONS or not MISSIONS[mid][3] or m.get("m"):
        return clan, False
    if mid in OFFER_POOL and mid not in (m.get("pool") or []):
        return clan, False                                  # (a pool mission only from the pool rolled for this choice)
    rep = m.get("rep", {})
    if rep.get(str(mid), 0) >= MISSION_REPEAT_MAX and any(rep.get(str(i), 0) < MISSION_REPEAT_MAX for i, v in MISSIONS.items() if v[3]):
        return clan, False                                  # (the 2013 list greys out a mission completed five times)
    s = event_window(clan["day"])
    left = s + EVENT_LEN - clan["day"] if s >= 0 else MISSION_DAYS
    m["m"] = {"id": mid, "left": left, "prog": 0, "ev": s, "sz": clan["healthy"] + clan["hungry"] + clan["sick"]}
    m.pop("pool", None)                                     # the next choice rolls a new pool
    clan["meta"] = json.dumps(m, separators=(",", ":"))
    save(c, tid, clan)
    return clan, True


# ------------------------------------------------------------------ boosters
def booster_counts(c, tid):
    """{bid: owned} for every booster id (0 owned = 0)."""
    ensure(c)
    out = {b: 0 for b in BOOSTERS}
    for bid, n in c.execute("SELECT bid, n FROM boosters WHERE token_id=?", (tid,)):
        if bid in out:
            out[bid] = n
    return out


def booster_grant(c, tid, bid, n=1):
    if bid not in BOOSTERS or n <= 0:
        return 0
    ensure(c)
    cur = booster_counts(c, tid)[bid]
    new = min(BOOSTER_MAX, cur + n)
    c.execute("INSERT INTO boosters(token_id,bid,n) VALUES(?,?,?) ON CONFLICT(token_id,bid) DO UPDATE SET n=excluded.n",
              (tid, bid, new))
    return new - cur


def booster_consume(c, tid, bid):
    """Use one up. True when the player had it."""
    if bid not in BOOSTERS or booster_counts(c, tid)[bid] <= 0:
        return False
    c.execute("UPDATE boosters SET n = n - 1 WHERE token_id=? AND bid=? AND n > 0", (tid, bid))
    return True


def booster_next(clan):
    """Survivors still missing for the clan's next booster ("+5 NEXT ONE-USE BOOSTER")."""
    size = clan["healthy"] + clan["hungry"] + clan["sick"]
    return max(1, (max(clan.get("boost_hi", 0), size // BOOSTER_EVERY) + 1) * BOOSTER_EVERY - size)


def meta_text(c, tid, pick=0, active=0):
    """Reply to the client ext (op 0xE9): booster counts bc1..bc7, bp = the pick for the next match, ba = the
    booster in use this match, bn = survivors to the next booster. Mission: mi / mp / ml / mz, mr<id> = completions, mg1..3 = the
    running mission's tier goals (2013 lists, not scaled), mev = 1 when it is an event's training."""
    clan = load(c, tid)
    cnt = booster_counts(c, tid)
    f = ["v=1"] + ["bc%d=%d" % (b, cnt[b]) for b in sorted(BOOSTERS)]
    f += ["bp=%d" % pick, "ba=%d" % active, "bn=%d" % booster_next(clan)]
    meta = meta_of(clan)
    m = meta.get("m") or {}
    if not m and clan["status"] == ALIVE:
        pool = [i for i in (meta.get("pool") or []) if i in OFFER_POOL]
        if not pool:                                        # roll the pool missions on offer for this choice (kept until one is chosen)
            pool = sorted(random.sample(OFFER_POOL, random.choice(EXEC_POOL_PICK)))
            meta["pool"] = pool
            clan["meta"] = json.dumps(meta, separators=(",", ":"))
            save(c, tid, clan)
            print("mission: pool rolled for", str(tid)[:8], [MISSIONS[i][0] for i in pool], flush=True)
        f += ["p%d=%d" % (k + 1, i) for k, i in enumerate(pool[:3])]
    f += ["mi=%d" % m.get("id", 0), "mp=%d" % m.get("prog", 0), "ml=%d" % m.get("left", 0),
          "mz=%d" % (m.get("sz", 0) if m else clan["healthy"] + clan["hungry"] + clan["sick"])]
    f += ["mr%d=%d" % (int(k), n) for k, n in sorted(meta.get("rep", {}).items(), key=lambda kv: int(kv[0])) if n]
    if m:
        g = mission_goals(m["id"], meta.get("rep", {}).get(str(m["id"]), 0))
        f += ["mg1=%d" % g[0], "mg2=%d" % g[1], "mg3=%d" % g[2], "mev=%d" % (1 if m.get("ev", -1) >= 0 else 0)]
    try:
        r = json.loads(clan.get("last_result") or "{}")
    except ValueError:
        r = {}
    if r.get("mi"):                              # what the last match did to the mission (post-match page)
        f += ["lmi=%d" % r["mi"], "lmp=%d" % r.get("mp", 0), "lmt=%d" % r.get("mt", 0), "lms=%d" % r.get("ms", 0),
              "lmb=%d" % len(r.get("boosters", [])), "lml=%d" % r.get("ml", 0), "lmd=%d" % r.get("day", -1),
              "lmz=%d" % r.get("mz", 0), "lmx=%d" % r.get("mlost", 0)]
    return " ".join(f)


def match_tag(mid):
    """Small positive int that changes with every resolved match (0 = none yet): the client tells a NEW result from the previous one with it.
    A day that does not count (idle / late-join multiplier) leaves the day number unchanged, so `lday` alone cannot."""
    if not mid:
        return 0
    return (zlib.crc32(str(mid).encode("utf-8", "ignore")) & 0x3fffffff) | 1


def state_text(clan):
    """Reply to the client ext (op 0xE1): one line of key=value, ints only."""
    n = clan["healthy"] + clan["hungry"] + clan["sick"]
    try:
        r = json.loads(clan.get("last_result") or "{}")
    except ValueError:
        r = {}
    f = {"v": 1, "fac": clan["faction"], "st": clan["status"], "day": clan["day"],
         "h": clan["healthy"], "hu": clan["hungry"], "s": clan["sick"], "need": needed(n),
         "wk": rank_of(clan)[1], "rk": rank_of(clan)[0], "dt": int(clan.get("days_total") or 0),
         "lday": r.get("day", -1), "lparts": r.get("parts", 0), "lsup": r.get("supplies", 0),
         "lneed": r.get("needed", 0), "lgain": r.get("gained", 0), "ldied": r.get("died", 0),
         "lhungry": r.get("new_hungry", 0), "lsick": r.get("new_sick", 0), "lheal": r.get("healed", 0),
         "lleft": r.get("left", 0),
         "lmh": match_tag(clan.get("last_mid"))}
    ek, en = event_today(clan["day"]) if clan["status"] == ALIVE else (0, 0)
    f.update(ev=ek, evn=en, levk=r.get("evk", 0), levn=r.get("evn", 0), levl=r.get("evl", 0),
             levg=r.get("evg", 0), levt=r.get("evt", 0),
             mx=max(meta_of(clan).get("max", 0), n), rw=clan.get("runs_won", 0), rl=clan.get("runs_lost", 0))
    meta = meta_of(clan)
    m = meta.get("m")
    g = mission_goals(m["id"], meta.get("rep", {}).get(str(m["id"]), 0)) if m else attack_goals(n)
    f.update(ag1=g[0], ag2=g[1], ag3=g[2])
    return " ".join(f"{k}={v}" for k, v in f.items())
