"""Achievements (Steam-style): definitions, booking and storage. The daemon is the only place that unlocks one.

Inputs, per player and match (tools/daemon.py):
- the 0xE2 match report counts (mission labels 1..6 + the running mission, extended labels 21..24, 33 bottles), after the anti-cheat clamp;
- the 0xA9 achievement report (the ext's full mission counters 1..63 and the achievement-only counters 64..127, ACH_LABELS);
- the match result (win / loss / unknown), early leave, late join;
- the clan day (state before / after + the day's result dict of clan.apply_match) and the side choice.

Both reports of a match can arrive in either order and be re-sent. book_match() credits per label only what is above what that match
already credited (the caller keeps `done`), so a re-send or the second report never counts twice.

Storage (same sqlite db as the clans, keyed like the clan: clan_key = "s:<steamid>" when known):
  ach_count(key, lab, n)    lifetime counters (labels 1..127 and the derived counters >= 200 below)
  ach(key, aid, unlocked)   unlocked achievements (unix time)
A goal change re-evaluates from the counters on the next booking / read (refresh()).
"""
import sqlite3
import time

# ---- labels -------------------------------------------------------------------------------------------------------------------------
# 1..63: the ext's mission counters (clan.py MISSIONS ids; 21..24 / 33 come from 0xE2 only)
L_DOWNS, L_EXECS, L_REVIVES, L_HEADSHOTS, L_MARKS, L_HEALS, L_SPECIAL = 1, 2, 3, 4, 5, 6, 7
L_MOLOTOV, L_NAIL, L_GIFT, L_MELEE_DOWN, L_SHIV, L_LONG = 8, 9, 10, 11, 12, 13
L_SHORTY_DOWN, L_HUNT_DOWN, L_BOW_DOWN = 16, 17, 20
L_TIMES_DOWNED, L_DEATHS, L_STREAK, L_TOPWEAPON = 21, 22, 23, 24
L_BOTTLES = 33
L_REVOLVER_EXEC = 49
# 64..127: achievement-only counters the ext counts (tools/ext/achieve.c)
L_SE_CROWBAR, L_SE_HAMMER, L_SE_MACHETE, L_SE_HATCHET, L_SE_BAT, L_SE_2X4, L_SE_PIPE, L_SE_WRENCH, L_SE_CLUB, L_SE_FISTS = range(64, 74)
L_OWN_MOLOTOV = 74            # we went down to our own molotov
L_BOW_TELL = 75               # a bow headshot down from 40 m or more
L_DODGES = 76                 # melee blows dodged
L_PIN_ESC = 77                # pins escaped
L_PIN_ESC_LOW = 78            # pins escaped with 10 health or less
L_LAST_STANDING = 79          # "Last One Standing" awards
L_STREAK_STOP = 80            # "Streak Stopped" awards
L_HURT = 81                   # "Kill While Hurt" awards
L_RETALIATION = 82
L_TEAM_REVENGE = 83
L_RAPID = 84                  # "Rapid Kill" awards
L_LOCKBOX = 85                # lockboxes opened (Interrogation)
L_CRAFT = 86                  # items crafted
L_COMEBACK = 87               # "Comeback Bonus" awards
L_XBOW_TELL = 88              # a crossbow headshot down from 40 m or more
L_COUNTER = 89                # dodge counters landed (the blow after a dodge)
L_EXECUTED = 90               # we were executed (victim of an E execution)
SE_WEAPON_LABELS = tuple(range(L_SE_CROWBAR, L_SE_CLUB + 1))
DOWN_KIND_LABELS = (L_MOLOTOV, L_NAIL, L_MELEE_DOWN, L_LONG, 14, 15, L_SHORTY_DOWN, L_HUNT_DOWN, 18, 19, L_BOW_DOWN)
# derived counters (daemon)
D_MATCHES, D_WINS, D_LOSSES, D_MISSION_TOP, D_WON_WLF, D_WON_SERA, D_WON_ANY = 200, 201, 202, 203, 204, 205, 206
MAX_PER_MATCH = 60            # no label counts more than this in one match (anti-cheat: a forged report gains little)

WLF, SERAPHITES = 1, 2        # clan.py faction ids
ALIVE, DEAD, WON = 1, 2, 3    # clan.py status


def _c(lab):
    f = lambda cnt, m: cnt.get(lab, 0)              # noqa: E731
    f.lab = lab                                     # (live_rules: a plain lifetime counter the ext can follow in the match)
    return f


def _all_se(cnt, m):
    return sum(1 for lab in SE_WEAPON_LABELS[:9] if cnt.get(lab, 0) > 0)


# ---- the table ----------------------------------------------------------------------------------------------------------------------
# Goals from live data (snapshot, 1218 player-matches): per match ~10 downs, ~5 executions, ~2 headshots, 0.6 revives;
# matches per player p50 7 / p75 29 / p90 67. Lifetime goals take a regular (p75-p90) player tens of matches; one-match feats need a
# top-few-percent match. A per-action goal = 15+ matches of a player who goes for it (a revolver main executes up to
# ~10 a match, so 150). Ids keep their first goal (stored unlocks and art are keyed by id).
# kind "count": progress = prog(lifetime counters, None) (capped at goal); kind "match": one match's facts satisfy test(m) (goal 1);
# kind "clan": unlocked by book_clan / book_side (goal 1, or a counter goal for ranks).
# group: melee / weapon / skill / stats / clan / secret (the UI's order).
ACH = []


def _a(aid, group, title, desc, kind, goal=1, prog=None, test=None, hidden=False, art="", live=None):
    """live (match kinds): (label, n) = the test is "label >= n in this match" and the ext may check it during the match (live_rules)."""
    ACH.append({"id": aid, "group": group, "title": title, "desc": desc, "kind": kind, "goal": goal, "prog": prog, "test": test,
                "hidden": hidden, "art": art, "live": live})


# melee mastery
_a("se_crowbar", "melee", "I'M A FREE MAN", "50 Special Executions with a crowbar in your hand.", "count", 50, _c(L_SE_CROWBAR))
_a("se_hammer", "melee", "HAMMER TIME", "50 Special Executions with a hammer in your hand.", "count", 50, _c(L_SE_HAMMER))
_a("se_machete", "melee", "MACHETE DON'T TEXT", "50 Special Executions with a machete in your hand.", "count", 50, _c(L_SE_MACHETE))
_a("se_hatchet", "melee", "HERE'S JOHNNY", "50 Special Executions with a hatchet in your hand.", "count", 50, _c(L_SE_HATCHET))
_a("se_bat", "melee", "BATTER UP", "50 Special Executions with a baseball bat in your hand.", "count", 50, _c(L_SE_BAT))
_a("se_2x4", "melee", "BOARD MEETING", "50 Special Executions with a 2x4 in your hand.", "count", 50, _c(L_SE_2X4))
_a("se_pipe", "melee", "PETER PIPER", "50 Special Executions with a pipe in your hand.", "count", 50, _c(L_SE_PIPE))
_a("se_wrench", "melee", "IT'S-A ME", "50 Special Executions with a pipe wrench in your hand.", "count", 50, _c(L_SE_WRENCH))
_a("se_club", "melee", "BONK", "50 Special Executions with a club or baton in your hand.", "count", 50, _c(L_SE_CLUB))
_a("se_fists", "melee", "FALCON PUNCH", "50 Special Executions with your bare hands.", "count", 50, _c(L_SE_FISTS))
_a("shiv_25", "melee", "SHIV HAPPENS", "75 shiv kills.", "count", 75, _c(L_SHIV))
_a("melee_all", "melee", "JACK OF ALL BLADES", "A Special Execution with every melee weapon.", "count", 9, _all_se)
# weapon feats
_a("bow_50", "weapon", "ROBIN HOOD", "Down 250 enemies with the bow.", "count", 250, _c(L_BOW_DOWN))
_a("bow_tell", "weapon", "MADE BORIS PROUD", "Down an enemy with a bow headshot from 40 m or more.", "count", 1, _c(L_BOW_TELL))
_a("xbow_tell", "weapon", "WILLIAM TELL", "Down an enemy with a crossbow headshot from 40 m or more.", "count", 1, _c(L_XBOW_TELL))
_a("revolver_10", "weapon", "DO YOU FEEL LUCKY", "150 executions with the revolver.", "count", 150, _c(L_REVOLVER_EXEC))
_a("shorty_25", "weapon", "BOOMSTICK", "Down 200 enemies with the Shorty.", "count", 200, _c(L_SHORTY_DOWN))
_a("hunting_50", "weapon", "ONE SHOT, ONE DOWN", "Down 250 enemies with the hunting rifle.", "count", 250, _c(L_HUNT_DOWN))
_a("long_50", "weapon", "EAGLE EYE", "250 downs from 30 m or more.", "count", 250, _c(L_LONG))
_a("molotov_25", "weapon", "FIRE IN THE HOLE", "Down 50 enemies with molotovs.", "count", 50, _c(L_MOLOTOV))
_a("nail_25", "weapon", "PIPE DOWN", "Down 50 enemies with pipe bombs.", "count", 50, _c(L_NAIL))
_a("head_100", "weapon", "HEADHUNTER", "250 headshots.", "count", 250, _c(L_HEADSHOTS))
# skill feats
_a("dodge_50", "skill", "FLOAT LIKE A BUTTERFLY", "Dodge 250 melee blows.", "count", 250, _c(L_DODGES))
_a("counter_100", "skill", "STING LIKE A BEE", "Land 100 counters after a dodge.", "count", 100, _c(L_COUNTER))
_a("dodge_5", "skill", "NOT EVEN CLOSE", "Dodge 10 melee blows in one match.", "match", test=lambda m: m.get(L_DODGES, 0) >= 10,
   live=(L_DODGES, 10))
_a("pin_10", "skill", "SLIPPERY", "Escape 25 pins.", "count", 25, _c(L_PIN_ESC))
_a("pin_low", "skill", "NOT TODAY", "Escape a pin with 10 health or less.", "count", 1, _c(L_PIN_ESC_LOW), hidden=True)
_a("streak_10", "skill", "UNSTOPPABLE", "10 downs in a row without going down.", "match", test=lambda m: m.get(L_STREAK, 0) >= 10)
_a("stopper_10", "skill", "BUZZKILL", "End 10 enemy streaks of 6 or more.", "count", 10, _c(L_STREAK_STOP))
_a("hurt_25", "skill", "'TIS BUT A SCRATCH", "Down 50 enemies at 30% health or less.", "count", 50, _c(L_HURT))
_a("rapid_25", "skill", "DOUBLE TAP", "100 Rapid Kills: two downs within 10 seconds.", "count", 100, _c(L_RAPID))
_a("payback_25", "skill", "PAYBACK", "Down the enemy who downed you, 75 times.", "count", 75, _c(L_RETALIATION))
_a("avenger_25", "skill", "AVENGER", "Avenge a downed teammate 75 times.", "count", 75, _c(L_TEAM_REVENGE))
_a("flawless", "skill", "UNTOUCHABLE", "Win a match with 5 or more downs and no deaths.", "match",
   test=lambda m: m.get("win") is True and m.get(L_DOWNS, 0) >= 5 and m.get(L_DEATHS, 0) == 0 and m.get(L_TIMES_DOWNED, 0) == 0)
_a("last_alive", "skill", "THE LAST OF US", "Be the Last One Standing 10 times.", "count", 10, _c(L_LAST_STANDING))
_a("comeback", "skill", "COMEBACK KID", "Win a match your team was losing.", "match",   # a Comeback Bonus (behind on lives) alone is no win
   test=lambda m: m.get("win") is True and m.get(L_COMEBACK, 0) > 0)
_a("melee_only", "skill", "WHO NEEDS GUNS", "Win a match where all of your 10 or more downs were melee.", "match", hidden=True,
   test=lambda m: m.get("win") is True and m.get(L_DOWNS, 0) >= 10 and m.get(L_MELEE_DOWN, 0) >= m.get(L_DOWNS, 0))
# stat milestones
_a("raid_1", "stats", "FIRST RAID", "Finish your first match.", "count", 1, _c(D_MATCHES))
_a("raid_100", "stats", "SEASONED", "Finish 100 matches.", "count", 100, _c(D_MATCHES))
_a("raid_500", "stats", "LIFER", "Finish 500 matches.", "count", 500, _c(D_MATCHES))
_a("win_50", "stats", "TOP DOG", "Win 50 matches.", "count", 50, _c(D_WINS))
_a("down_100", "stats", "BODY COUNT", "Down 500 enemies.", "count", 500, _c(L_DOWNS))
_a("down_1000", "stats", "WALKING ARSENAL", "Down 2,500 enemies.", "count", 2500, _c(L_DOWNS))
_a("exec_50", "stats", "EXECUTIONER", "250 Special Executions.", "count", 250, _c(L_SPECIAL))
_a("revive_50", "stats", "NO ONE LEFT BEHIND", "Revive 50 teammates.", "count", 50, _c(L_REVIVES))
_a("heal_50", "stats", "FIELD MEDIC", "Heal teammates 100 times.", "count", 100, _c(L_HEALS))
_a("gift_25", "stats", "CARE PACKAGE", "Give 50 crafted items to teammates.", "count", 50, _c(L_GIFT))
_a("mark_200", "stats", "LISTEN MODE", "Mark 1,000 enemies.", "count", 1000, _c(L_MARKS))
_a("craft_100", "stats", "MACGYVER", "Craft 300 items.", "count", 300, _c(L_CRAFT))
_a("bottle_50", "stats", "SCAVENGER", "Pick up 150 supply bottles.", "count", 150, _c(L_BOTTLES))
_a("loss_25", "stats", "ENDURE AND SURVIVE", "Lose 25 matches. Keep going.", "count", 25, _c(D_LOSSES), hidden=True)
# clan and story
_a("side", "clan", "PICK A SIDE", "Choose your side for the first time.", "clan")
_a("grave_1", "clan", "FIRST GRAVE", "Lose your first clan member.", "clan")
_a("weeks_12", "clan", "TWELVE WEEKS", "Survive all 12 weeks for the first time.", "count", 1, _c(D_WON_ANY))
_a("wlf_12", "clan", "WOLF PACK", "Survive 12 weeks as the WLF.", "count", 1, _c(D_WON_WLF))
_a("sera_12", "clan", "THE PROPHET PROVIDES", "Survive 12 weeks as the Seraphites.", "count", 1, _c(D_WON_SERA))
_a("both_12", "clan", "BOTH SIDES NOW", "Survive 12 weeks with both factions.", "count", 2,
   lambda cnt, m: min(1, cnt.get(D_WON_WLF, 0)) + min(1, cnt.get(D_WON_SERA, 0)))
_a("wiped", "clan", "NOTHING LEFT", "Lose every member of a clan.", "clan")
# weeks survived in total, over every journey (days_total // 7, the number next to the rank badge; the rank itself is the badge, 1..10).
# The ids stay rank_* (unlocked rows, icons, the loc keys).
for _r in (1, 5, 10, 25, 50, 100):
    # titles: SURVIVE A WEEK, SURVIVE A TOTAL OF 5 WEEKS, ... SURVIVE A TOTAL OF 100 WEEKS
    _t = "SURVIVE A WEEK" if _r == 1 else "SURVIVE A TOTAL OF %d WEEKS" % _r
    _a("rank_%d" % _r, "clan", _t, "Survive %d %s in total." % (_r, "week" if _r == 1 else "weeks"), "rank", _r)
_a("haven", "clan", "SAFE HAVEN", "Grow a clan to 100 survivors.", "clan")
_a("hold_line", "clan", "HOLD THE LINE", "Finish a raider attack at the top tier.", "clan")
_a("missions_10", "clan", "OVERACHIEVER", "Finish 10 clan missions at the top tier.", "count", 10, _c(D_MISSION_TOP))
# funny / hidden
_a("darwin", "secret", "DARWIN AWARD", "Go down to your own molotov.", "count", 1, _c(L_OWN_MOLOTOV), hidden=True)
_a("reaper", "secret", "DON'T FEAR THE REAPER", "Get executed 100 times.", "count", 100, _c(L_EXECUTED), hidden=True)
_a("pacifist", "secret", "PACIFIST", "Win a match with no downs and 3 or more revives.", "match", hidden=True,
   test=lambda m: m.get("win") is True and m.get(L_DOWNS, 0) == 0 and m.get(L_REVIVES, 0) >= 3)
_a("late_win", "secret", "FASHIONABLY LATE", "Join a match in progress and win it.", "match", hidden=True,
   test=lambda m: m.get("win") is True and bool(m.get("late")))
_a("lockbox_10", "secret", "SAFECRACKER", "Open 25 lockboxes in Interrogation.", "count", 25, _c(L_LOCKBOX))

BY_ID = {a["id"]: a for a in ACH}
assert len(BY_ID) == len(ACH), "duplicate achievement id"
for _x in ACH:
    assert _x["live"] is None or _x["test"]({_x["live"][0]: _x["live"][1]}) and not _x["test"]({_x["live"][0]: _x["live"][1] - 1}), _x["id"]

# ---- live unlocks ---------
# The ext knows the table (progress / goal per achievement, op 0xAA) and this match's counters, so it sees the moment a goal is crossed; it then
# sends op 0xAB (the counters so far) and the daemon books them (book_live) and answers with the table: the unlock card shows in the match.
# The daemon still decides every unlock. Live: the plain lifetime counters of the ext's labels, JACK OF ALL BLADES and the one-match counts
# with a `live` rule. Not live (match end, as before): the 0xE2-only labels the ext does not keep during the match (21..24, 33), the derived
# counters (matches, wins, losses, clan), the win / leave tests, ranks and the clan / side ones.
LIVE_SKIP = (21, 22, 23, 24, 33)                    # 0xE2 report only (times downed, deaths, streak, top weapon, bottles)


def live_rules():
    """[(id, kind, label, goal)] the ext checks during a match. kind: "count" = lifetime label >= goal, "allse" = the SE weapon labels with any
    count >= goal (label 0), "match" = this match's label >= goal."""
    out = []
    for a in ACH:
        lab = getattr(a["prog"], "lab", None)
        if a["kind"] == "count" and lab is not None and 1 <= lab <= 127 and lab not in LIVE_SKIP:
            out.append((a["id"], "count", lab, a["goal"]))
        elif a["kind"] == "count" and a["prog"] is _all_se:
            out.append((a["id"], "allse", 0, a["goal"]))
        elif a["kind"] == "match" and a["live"]:
            out.append((a["id"], "match", a["live"][0], a["live"][1]))
    return out


def ext_header():
    """tools/ext/ach_live.h (python tools/achievements.py --ext-header; test_achievements checks it is current)."""
    k = {"count": 0, "allse": 1, "match": 2}
    rs = live_rules()
    lines = ["// generated by tools/achievements.py --ext-header - do not edit. The achievements the ext checks during a match (achieve.c ach_live_tick):",
             "// kind 0 = lifetime label >= goal, 1 = Special Execution weapons (ACH_LIVE_SE labels) with any count >= goal, 2 = this match's label >= goal.",
             "#define ACH_LIVE_N %d" % len(rs),
             "#define ACH_LIVE_SE_N %d" % len(SE_WEAPON_LABELS[:9]),
             "static const unsigned char ACH_LIVE_SE[ACH_LIVE_SE_N] = {%s};" % ", ".join(str(x) for x in SE_WEAPON_LABELS[:9]),
             "static const struct { const char *id; unsigned char kind, lab; unsigned short goal; } ACH_LIVE[ACH_LIVE_N] = {"]
    for aid, kind, lab, goal in rs:
        lines.append('    {"%s", %d, %d, %d},' % (aid, k[kind], lab, goal))
    lines.append("};")
    return "\n".join(lines) + "\n"

SCHEMA = ("CREATE TABLE IF NOT EXISTS ach_count(key TEXT, lab INT, n INT DEFAULT 0, PRIMARY KEY(key, lab))",
          "CREATE TABLE IF NOT EXISTS ach(key TEXT, aid TEXT, unlocked REAL, PRIMARY KEY(key, aid))")


def ensure(c):
    for s in SCHEMA:
        try:
            c.execute(s)
        except sqlite3.OperationalError:                           # a read-only connection (the website: tools/web/web.py opens mode=ro) - the
            pass                                                   # reads below then find the tables or return nothing


def _q(c, sql, args):
    try:
        return list(c.execute(sql, args))
    except sqlite3.OperationalError:                               # no such table yet (read-only, nobody unlocked anything)
        return []


def counters(c, key):
    ensure(c)
    return {int(lab): int(n) for lab, n in _q(c, "SELECT lab, n FROM ach_count WHERE key=?", (key,))}


def unlocked(c, key):
    ensure(c)
    return {aid: float(t) for aid, t in _q(c, "SELECT aid, unlocked FROM ach WHERE key=?", (key,))}


def _add(c, key, lab, n):
    if n > 0:
        c.execute("INSERT INTO ach_count(key, lab, n) VALUES(?,?,?) ON CONFLICT(key, lab) DO UPDATE SET n = n + excluded.n", (key, int(lab), int(n)))


def _set_max(c, key, lab, n):
    c.execute("INSERT INTO ach_count(key, lab, n) VALUES(?,?,?) ON CONFLICT(key, lab) DO UPDATE SET n = MAX(n, excluded.n)", (key, int(lab), int(n)))


def _unlock(c, key, aid, now, got):
    if aid not in BY_ID:
        return
    cur = c.execute("INSERT OR IGNORE INTO ach(key, aid, unlocked) VALUES(?,?,?)", (key, aid, now))
    if cur.rowcount:
        got.append(aid)


def refresh(c, key, now=None, match=None, rank=None):
    """Unlock every counter achievement whose goal is reached (and the match ones `match` satisfies). Returns the newly unlocked ids."""
    now = time.time() if now is None else now
    cnt, have, got = counters(c, key), unlocked(c, key), []
    for a in ACH:
        if a["id"] in have:
            continue
        if a["kind"] == "count" and a["prog"](cnt, None) >= a["goal"]:
            _unlock(c, key, a["id"], now, got)
        elif a["kind"] == "match" and match is not None and a["test"](match):
            _unlock(c, key, a["id"], now, got)
        elif a["kind"] == "rank" and rank is not None and rank >= a["goal"]:
            _unlock(c, key, a["id"], now, got)
    return got


def sanitize(counts):
    """One match's counters as the daemon may trust them: ints, labels 1..127, at most MAX_PER_MATCH each (23 = best streak is a value), the
    weapon-kind downs never above the downs, the Special Execution weapon split never above the Special Executions / executions."""
    out = {}
    for k, v in (counts or {}).items():
        try:
            k, v = int(k), int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= k <= 127 and v > 0 and k != L_TOPWEAPON:
            out[k] = min(v, MAX_PER_MATCH)
    downs = out.get(L_DOWNS, 0)
    for lab in DOWN_KIND_LABELS + (L_BOW_TELL,):
        if lab in out:
            out[lab] = min(out[lab], downs)
    execs = max(out.get(L_SPECIAL, 0), out.get(L_EXECS, 0))
    se = sum(out.get(lab, 0) for lab in SE_WEAPON_LABELS)
    if se > execs:
        for lab in SE_WEAPON_LABELS:                       # scale down, keep at least what fits
            if lab in out:
                out[lab] = out[lab] * execs // se
                if out[lab] <= 0:
                    del out[lab]
    if out.get(L_PIN_ESC_LOW, 0) > out.get(L_PIN_ESC, 0):
        out[L_PIN_ESC_LOW] = out.get(L_PIN_ESC, 0)
    return out


def book_match(c, key, counts, done, win=None, left=False, late=False, first=True, now=None):
    """Credit one match's counters. `done` = {label: n} this match already credited (updated in place, the caller keeps it per (token, mid));
    first = the match's first booking (books the match / win / loss counters). Returns the newly unlocked ids."""
    ensure(c)
    cnt = sanitize(counts)
    for lab, n in cnt.items():
        if lab == L_STREAK:
            if n > done.get(lab, 0):
                _set_max(c, key, lab, n)
                done[lab] = n
            continue
        add = n - done.get(lab, 0)
        if add > 0:
            _add(c, key, lab, add)
            done[lab] = n
    if first and not left:
        _add(c, key, D_MATCHES, 1)
        if win is True:
            _add(c, key, D_WINS, 1)
        elif win is False:
            _add(c, key, D_LOSSES, 1)
    match = dict(done)
    match["win"] = win if not left else None
    match["late"] = bool(late)
    return refresh(c, key, now, match=match)


def book_live(c, key, counts, done, now=None):
    """Op 0xAB: this match's counters so far (labels 1..127 but LIVE_SKIP). Credited like book_match (only what is above `done`, the same dict the
    match end uses: nothing counts twice), no match / win / loss counters, the one-match tests with the win unknown. Returns the new unlocks."""
    ensure(c)
    for lab, n in sanitize(counts).items():
        if lab in LIVE_SKIP:
            continue
        add = n - done.get(lab, 0)
        if add > 0:
            _add(c, key, lab, add)
            done[lab] = n
    match = dict(done)
    match["win"] = None
    match["late"] = False
    return refresh(c, key, now, match=match)


def settle(c, key, auth, done, labels):
    """The match's authoritative counts arrived (the clamped 0xE2 report): a label the live reports credited above them is taken back to them
    (an unlock it gave stays). Labels the live reports never credited are left to book_match."""
    ensure(c)
    for lab in labels:
        v = int((auth or {}).get(lab, 0))
        if lab in done and done[lab] > v:
            c.execute("UPDATE ach_count SET n = MAX(0, n - ?) WHERE key=? AND lab=?", (int(done[lab] - v), key, int(lab)))
            done[lab] = v


def book_side(c, key, now=None):
    ensure(c)
    got = []
    _unlock(c, key, "side", time.time() if now is None else now, got)
    return got


def book_clan(c, key, before, after, r, rank_weeks=None, now=None):
    """A booked clan day: before / after = clan rows (dicts), r = the day's result (clan.resolve_day / _event_step fields)."""
    ensure(c)
    now = time.time() if now is None else now
    got = []
    r = r or {}
    if int(r.get("died", 0)) > 0:
        _unlock(c, key, "grave_1", now, got)
    st0, st1 = int((before or {}).get("status", 0)), int((after or {}).get("status", 0))
    if st1 == DEAD and st0 != DEAD:
        _unlock(c, key, "wiped", now, got)
        if int(r.get("died", 0)) <= 0:                     # (a wipe always buries someone)
            _unlock(c, key, "grave_1", now, got)
    if st1 == WON and st0 != WON:
        _add(c, key, D_WON_ANY, 1)
        fac = int((after or {}).get("faction", 0))
        if fac == WLF:
            _add(c, key, D_WON_WLF, 1)
        elif fac == SERAPHITES:
            _add(c, key, D_WON_SERA, 1)
    size = sum(int((after or {}).get(k, 0) or 0) for k in ("healthy", "hungry", "sick"))
    if size >= 100:
        _unlock(c, key, "haven", now, got)
    if r.get("evk") == 2 and int(r.get("evt", 0)) >= 3:      # clan.EV_ATTACK settled at the top tier
        _unlock(c, key, "hold_line", now, got)
    if r.get("mdone") and int(r.get("mt", 0)) >= 3:
        _add(c, key, D_MISSION_TOP, 1)
    if rank_weeks is None and after:
        rank_weeks = int(after.get("days_total") or 0) // 7
    return got + [a for a in refresh(c, key, now, rank=rank_weeks) if a not in got]


def rows(c, key, rank_weeks=None):
    """[(achievement dict, progress, unlocked time or 0)] in table order, for the UIs."""
    cnt, have = counters(c, key), unlocked(c, key)
    out = []
    for a in ACH:
        if a["kind"] == "count":
            p = min(a["goal"], int(a["prog"](cnt, None)))
        elif a["kind"] == "rank":
            p = min(a["goal"], int(rank_weeks or 0))
        else:
            p = 0
        t = have.get(a["id"], 0.0)
        if t:
            p = a["goal"]
        out.append((a, p, t))
    return out


def _clean(s):
    return s.replace("|", "/").replace("\n", " ")


def wire_text(c, key, rank_weeks=None):
    """The 0xAA reply / launcher text. Line 1: 'ACH <unlocked> <total>'. Then one line per achievement in table order:
    id|group|unlocked unix (0 = locked)|progress|goal|hidden|title|description. A hidden locked one is sent as '?' title / description."""
    rs = rows(c, key, rank_weeks)
    lines = ["ACH %d %d" % (sum(1 for _, _, t in rs if t), len(rs))]
    for a, p, t in rs:
        hid = a["hidden"] and not t
        lines.append("|".join((a["id"], a["group"], str(int(t)), str(0 if hid else p), str(a["goal"]), "1" if a["hidden"] else "0",
                               "?" if hid else _clean(a["title"]), "Hidden achievement" if hid else _clean(a["desc"]))))
    return "\n".join(lines) + "\n"


def public_rows(c, key, rank_weeks=None):
    """The website profile: dicts (hidden locked ones masked)."""
    out = []
    for a, p, t in rows(c, key, rank_weeks):
        hid = a["hidden"] and not t
        out.append({"id": a["id"], "group": a["group"], "title": "?" if hid else a["title"], "desc": "Hidden achievement" if hid else a["desc"],
                    "goal": a["goal"], "prog": 0 if hid else p, "unlocked": int(t), "hidden": bool(a["hidden"])})
    return out


if __name__ == "__main__":
    import os
    import sys
    if sys.argv[1:] == ["--ext-header"]:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ext", "ach_live.h")
        open(out, "w", encoding="utf-8", newline="\n").write(ext_header())
        print("ach_live.h: %d live rules" % len(live_rules()))
    else:
        raise SystemExit("python tools/achievements.py --ext-header")
