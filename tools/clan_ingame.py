"""The in-game CLAN page's data (tools/features/clan13_widgets.py, tools/ext/clan13.c): daemon op 0xB6 -> reply 0xB7, compact tab-separated lines.

  op 0xB6 [64B token][u8 language 0 en / 1 pl][u8 section 1 roster / 2 journal / 3 raids][u32 LE seen journal id][u16 LE seen raid day]  (the last two optional: NEW markers)
  reply 0xB7 = text("\\n"-separated lines, fields separated by TAB; no TAB / newline inside a field; <= ~14 KB)

Every section starts with  H week day faction(W/S) morale label alive worstSupplyDays(-1 none) daysDone clansWon clansLost largestClan
Section 4 (STATUS UPDATES): U name roleText state stateWord pid line  (<= 4 newest pending member status changes: clan_status.public)
Section 1 (ROSTER):  P name roleText stateCode(h/u/s/d/k) stateWord expr portraitId bond bondTypeWord tagline lately roleIcon      (<= 40 members)
Section 2 (JOURNAL): J id caption title body tone(good/warn/bad/info/"") arcId step day week portraitId name new(0/1) more   (<= 24 STORIES, newest first; only written stories)
                     L cardId day text new(0/1)     (a one-liner of the timeline, under the J row with that id, <= 3 per story, in time order; "more" on the J row counts the rest)
Section 5 (MATCH STATS of one raid, op 0xB6 with the u16 "seen raid day" slot = the raid's day; F / Triangle-Y on the RAIDS page):
                     X day map win(1/0/-) players        (the match header; players = rows below, 0 = no stats were recorded: a match from before the stats were recorded)
                     Q name team(0/1/-1) me(0/1) kills downs deaths revives execs headshots parts left(0/1) head    (a stat the client did not report = -1; <= 12, the asker's team first, then best parts first;
                       kills = enemies downed (label 1), downs = times the player was downed (label 21), deaths = label 22; head = the pool model id of the player's face, 0 = none: old daemons send 12 fields)
Section 3 (RAIDS):   S label stock days need   (5 rows: food water med ammo mat; days -1 = no need),
                     M day map win(1/0/-) sup need new gotCats(5 numbers) needCats(5 numbers)   (<= 8, newest first),
                     T matchDay qty name iconKey new   (loot of those matches)
Section 7 (END SCREEN, dead / won clans only; tools/ext/clanend.c): E kind(W/L) faces more remembered raidsWon raidsPlayed, then R name portraitId per face (<= 7)
Section 6 (JOURNAL, week pages; tools/clan_journal.py: ONE entry per clan day; the u16 "seen raid day" slot = the week whose text is wanted, 0 = the newest):
                     K week newestWeek            (the week whose paragraphs follow; the newest week that has an entry)
                     D day dow week id title tone(good/warn/bad/info) map win(1/0/-) sup need healthy hungry sick(-1 = unknown: an entry from before this field existed) sizeChange new(0/1)
                       (EVERY entry of the run, oldest first: the index of the week pages, <= 85 rows; day 0 = the founding, dow 0)
                     G day caption text           (the paragraphs of the days of week `week`, in reading order: THE RAID / SUPPLIES / THE CAMP / the event's name / NOTES)
                     Section 2 of a clan that has such entries carries them as J rows (one per day, newest first, caption "WEEK w - DAY d", no arc): older clients show the same journal.
Everything is the data the launcher's /clanfeed.json "chron" and /clan.json carry (clan_chronicle.public, clan_story.read_feed / read_people, the last result's
supplies); the strings are already in the player's language. Pure functions of a sqlite connection: read only."""
import json
import re

import clan
import clan_story
import clan_journal_entries
import clan_chronicle as CH
import clan_supply

ARC_RE = re.compile("^(?:DAY|DZIEŃ) (\\d+): ([^.]*)\\.\\s*([\\s\\S]*)$")
CAP = {"match_strong": "MATCH", "match_even": "MATCH", "match_bad": "MATCH", "match_downs": "MATCH", "haul_good": "SUPPLIES", "haul_short": "SUPPLIES", "ration": "RATIONS",
       "raid_prep": "NEXT RAID", "mourn": "LOST", "lastwords": "LAST WORDS", "sick_watch": "SICK BAY", "hunger": "HUNGER", "newcomer": "NEWCOMER", "kids": "CAMP", "quarrel": "CAMP",
       "quiet": "CAMP", "use_food": "STORES", "use_med": "STORES", "use_ammo": "STORES", "use_tool": "STORES", "saga_recap": "PREVIOUSLY"}
CAP_PL = {"MATCH": "MECZ", "SUPPLIES": "ZAPASY", "RATIONS": "RACJE", "NEXT RAID": "NASTĘPNY RAID", "LOST": "STRATA", "LAST WORDS": "OSTATNIE SŁOWA", "SICK BAY": "LAZARET",
          "HUNGER": "GŁÓD", "NEWCOMER": "NOWY", "CAMP": "OBOZ", "STORES": "ZAPASY", "CAMP LOG": "DZIENNIK OBOZU", "STORY": "HISTORIA", "RAID": "RAID", "KEEPSAKE": "PAMIĄTKA",
          "BIRTH": "NARODZINY", "LAST WISH": "OSTATNIE ŻYCZENIE", "BLAME": "WINA", "BETRAYAL": "ZDRADA", "PREVIOUSLY": "WCZEŚNIEJ", "GRIEF": "ŻAŁOBA", "WOUNDED": "RANNI", "BONDS": "WIĘZI", "PEOPLE": "LUDZIE", "SPORES": "ZARODNIKI", "STRANGER": "OBCY", "CARAVAN": "KARAWANA", "FIREFLY": "ŚWIETLIK", "BIRTHDAY": "URODZINY"}
ARC_TAG = {"missing": "RAID", "sick": "SICK BAY", "hung": "HUNGER", "new": "NEWCOMER", "keep": "KEEPSAKE", "birth": "BIRTH", "wish": "LAST WISH", "blame": "BLAME", "betray": "BETRAYAL", "spore": "SPORES", "stranger": "STRANGER", "caravan": "CARAVAN", "pendant": "FIREFLY", "birthday": "BIRTHDAY"}
TONE = {"match_strong": "good", "match_bad": "bad", "match_downs": "warn", "haul_good": "good", "haul_short": "warn", "ration": "warn", "raid_prep": "info", "mourn": "bad",
        "lastwords": "bad", "sick_watch": "warn", "hunger": "warn", "newcomer": "info", "kids": "good", "quarrel": "warn", "use_food": "good", "use_med": "warn", "use_ammo": "info", "saga_recap": "info"}
DIARY_TAG = {"ill": "SICK BAY", "mourn": "GRIEF", "raid": "RAID", "haul": "SUPPLIES"}
SAGA_TAG = {"saga_inj": "WOUNDED", "saga_grief": "GRIEF", "saga_rel": "BONDS", "saga_prof": "PEOPLE"}
MOOD_TONE = {"hopeful": "good", "cheerful": "good", "worried": "warn", "afraid": "warn", "desperate": "bad", "grieving": "bad", "grim": "bad", "despair": "bad"}
STATE_WORD = {"en": {"h": "HEALTHY", "u": "HUNGRY", "s": "SICK", "d": "DEPRESSED", "k": "IN SHOCK"}, "pl": {"h": "ZDROWY", "u": "GŁODNY", "s": "CHORY", "d": "PRZYGNĘBIONY", "k": "W SZOKU"}}
STATE_CODE = {"healthy": "h", "hungry": "u", "sick": "s", "depressed": "d", "shock": "k", "sad": "d", "injured": "d"}      # sad / injured have no letter of their own in the client: the calm grey-blue one of "depressed", with their own word (STATE_WORD2)
BOND_WORD = {"en": {"kin": "FAMILY", "friend": "FRIEND", "rival": "RIVAL", "love": "CLOSE", "mentor": "MENTOR"},
             "pl": {"kin": "RODZINA", "friend": "PRZYJACIEL", "rival": "RYWAL", "love": "BLISKI", "mentor": "MENTOR"}}
CAT_LABEL = {"en": ("FOOD", "WATER", "MEDICINE", "AMMO", "MATERIALS"), "pl": ("JEDZENIE", "WODA", "LEKI", "AMUNICJA", "MATERIAŁY")}
MAX_ROSTER, MAX_JOURNAL, MAX_MATCHES = 40, 24, 8
MAX_STATS = 12
STATS_KEEP_S = 60 * 86400.0                                         # the per-match player stats outlive the chronicle's 30 raids by far; older rows are dropped on a write
STATS_SCHEMA = ("CREATE TABLE IF NOT EXISTS match_stats(mid TEXT, token TEXT, name TEXT, team INTEGER DEFAULT -1, win INTEGER DEFAULT -1, map TEXT, "
                "kills INTEGER DEFAULT -1, downs INTEGER DEFAULT -1, deaths INTEGER DEFAULT -1, revives INTEGER DEFAULT -1, execs INTEGER DEFAULT -1, heads INTEGER DEFAULT -1, "
                "parts INTEGER DEFAULT -1, left INTEGER DEFAULT 0, ts REAL, PRIMARY KEY(mid, token))",)
# the stock icons the game ships as streaming/t2r/icons/c13-<id>.png (tools/models/make_icons.clan13_icons, from the launcher's clan-icons.js); an unknown loot icon is a keepsake
ICON_IDS = frozenset(['food', 'medicine', 'water', 'ammo', 'materials', 'pills', 'alcohol', 'binding', 'rag', 'scissors', 'canister', 'explosive', 'molotov', 'pipebomb', 'shiv', 'arrow', 'wrench', 'key', 'coins', 'parts', 'keepsake', 'journal', 'gasmask', 'pistolammo', 'rifleammo', 'shotgunammo', 'healthbar', 'animal', 'backpack', 'bandage', 'battery', 'binoculars', 'blade', 'blanket', 'book', 'boots', 'buttons', 'can-opener', 'candle', 'card', 'cards', 'chess', 'cloth', 'clothes', 'coffee', 'compass', 'crowbar', 'dogtag', 'eggs', 'filter', 'firewood', 'first-aid', 'fish', 'fishing', 'flashlight', 'fruit', 'fuel-can', 'grain', 'guitar', 'gun-part', 'hammer', 'harmonica', 'hatchet', 'herb', 'insulin', 'lighter', 'map', 'matches', 'music-box', 'nails', 'patch', 'pendant', 'perfume', 'photo', 'pipe', 'planks', 'pot', 'radio', 'ring', 'rope', 'salt', 'saw', 'seeds', 'sewing', 'shovel', 'sunglasses', 'sweets', 'tape-cassette', 'tape', 'tarp', 'thermos', 'toolbox', 'toy', 'trowel', 'vest', 'vinyl', 'watch', 'whetstone', 'wire'])


def _icon(k):
    k = str(k or "")
    return k if k in ICON_IDS else "keepsake"


def _t(s, n=0):
    s = re.sub(r"[\t\r\n|]+", " ", str(s if s is not None else "")).strip()
    return s[:n] if n else s


def _split(text):
    x = ARC_RE.match(str(text or ""))
    return (x.group(2), x.group(3)) if x else ("", str(text or ""))


def _first_sentences(text, n=170):
    t = _t(text)
    if len(t) <= n:
        return t
    cut = t[:n]
    k = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:k + 1] if k > 40 else cut.rsplit(" ", 1)[0] + "..."


def _dow(d):
    """A clan day (1..) as the day of its week (the header says WEEK n: DAY d with the day being played)."""
    try:
        d = int(d)
    except (TypeError, ValueError):
        return 0
    return (d - 1) % 7 + 1 if d > 0 else 0


def _clan_row(c, tid):
    try:
        return c.execute("SELECT faction, status, day FROM clans WHERE token_id=?", (tid,)).fetchone()
    except Exception:                                               # noqa: BLE001
        return None


def _last_result(c, tid):
    try:
        cl = clan.load(c, tid)
        return json.loads(cl.get("last_result") or "{}") or {}
    except Exception:                                               # noqa: BLE001
        return {}


def _header(row, camp, last, pub, lang):
    week, dow = clan.week_day(int(row[2]))
    mo = (camp or {}).get("morale") or {}
    sup = (last or {}).get("sup") or {}
    days = [int(v) for k, v in (sup.get("days") or {}).items() if k in clan_supply.CATS and (sup.get("need") or {}).get(k)]
    worst = min(days) if days else -1
    fk = "S" if int(row[0]) == clan.SERAPHITES else "W"
    label = mo.get("text") if lang == "pl" and mo.get("text") else mo.get("label", "")
    cl = (pub or {}).get("_clan") or {}
    return "H\t%d\t%d\t%s\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d" % (week, dow, fk, int(mo.get("value", 50)), _t(str(label).upper(), 24),
                                                              int((camp or {}).get("alive", len(pub.get("roster", [])))), worst,
                                                              int(row[2]), int(cl.get("won", 0)), int(cl.get("lost", 0)), int(cl.get("max", 0)))


LATELY_DAYS = 7                                                    # an entry older than this is no "lately": the member's current state is shown instead


def _sentence(head, names):
    """A journal headline (upper case) as a sentence: lower case, the members' names with their capital."""
    t = head.strip().lower()
    t = t[:1].upper() + t[1:]
    for n in sorted(names, key=len, reverse=True):
        t = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(n.lower()), n, t)
    import clan_continuity
    return clan_continuity.restore_case(t, clan_continuity.proper_nouns())


def _lately(r, feed, lang, cur_day, gender, names):
    """LATELY of a member, always self-contained and about THEM: the newest journal entry whose headline names them (the headline is the event itself), as
    "DAY n: Headline" - never a mid-story sentence without its trigger; when there is none within LATELY_DAYS days, the line of their current state (hungry, sick ...)."""
    name = r["name"]
    for m in feed:
        head, _b = _split(m.get("text", ""))
        if not head or not re.search(r"(?<!\w)%s(?!\w)" % re.escape(name), head, re.I):
            continue
        d = int(m.get("day") or 0)
        if cur_day - d > LATELY_DAYS:
            break                                                      # the newest one is old: nothing "lately"
        return "%s %d: %s" % ("DZIE\u0143" if lang == "pl" else "DAY", _dow(d), _t(_sentence(head, names), 140))
    code = {"hungry": 1, "sad": 2, "sick": 3, "injured": 5, "depressed": 8, "shock": 9}.get(r.get("state", ""), 0)
    if code:
        import clan_status
        return _t(clan_status.story_line({"c": code, "n": name, "g": gender, "ln": ""}, lang), 140)
    return ""


def _person_rows(pub, feed, lang, camp=None, cur_day=0):
    gender = {p["name"]: p.get("gender", "n") for p in (camp or {}).get("people", [])}
    names = [p["name"] for p in pub.get("roster", [])] + [d["name"] for d in (camp or {}).get("dead", [])]
    lines = []
    for r in pub.get("roster", [])[:MAX_ROSTER]:
        code = STATE_CODE.get(r.get("state", "healthy"), "h")
        pid = r.get("portrait", "")
        expr = pid.rsplit("/", 1)[-1] if pid else "neutral"
        lately = _lately(r, feed, lang, cur_day, gender.get(r["name"], "n"), names)
        bw = r.get("bondLabel") or ""                               # the UI word (clan_chronicle.bond_label), never the raw key (kin / mentor / rival / sweet)
        lines.append("P\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (_t(r["name"], 24), _t(str(r.get("roleText", r.get("role", ""))).upper(), 24), code,
                     STATE_WORD2[lang].get(r.get("state", ""), STATE_WORD[lang][code]), _t(expr, 12), _t(pid, 20), _t(r.get("bond"), 24), _t(bw, 16), _t(r.get("tagline"), 150), lately, _t(r.get("icon"), 12)))
    return lines


def _body(t):
    """A journal card body for the wire: up to 1500 chars (a whole day entry must show in game; the client's body field is 1720 bytes, clan13.h) cut at a sentence
    boundary; blank lines (paragraphs) become spaces - the wire is tab / newline separated."""
    t = _t(t)
    t = _first_sentences(t, 1500)
    while len(t.encode("utf-8")) > 1700:                           # Polish diacritics: more bytes than chars
        t = _first_sentences(t, max(60, len(t) - 120))
    return t


def _first_seen(ents, seen_id):
    """A first visit (no seen id yet): only the newest entry is NEW."""
    if seen_id or not ents:
        return seen_id
    older = [e["id"] for e in ents[:-1]]
    return max(older) if older else 0


def _journal_day_rows(ents, lang, seen_id=0):
    """Section 2 from the day entries (tools/clan_journal.py): one J row per clan day, newest first - the rows an older client's JOURNAL tab already draws."""
    seen_id = _first_seen(ents, seen_id)
    out = []
    wk, dy = ("TYDZIEŃ", "DZIEŃ") if lang == "pl" else ("WEEK", "DAY")
    for e in reversed(ents[-MAX_JOURNAL:]):
        cap = "%s %d - %s %d" % (wk, e["week"], dy, e["dow"]) if e["day"] > 0 else "%s 1" % wk
        body = " ".join(t for _c, t in e["paras"])
        out.append("J	%d	%s	%s	%s	%s		0	%d	%d			%d	0" % (e["id"], _t(cap, 60), _t(e["title"], 90).upper(), _body(body), e["tone"],
                                                                    e["dow"], e["week"], 1 if e["id"] > seen_id else 0))
    return out


def _journal_week_rows(ents, lang, seen_id=0, week=0):
    """Section 6: the index of every entry (D) and the paragraphs (G) of one week."""
    seen_id = _first_seen(ents, seen_id)
    top = max([e["week"] for e in ents] or [1])
    week = top if week <= 0 or week > top else week
    out = ["K	%d	%d" % (week, top)]
    for e in ents:
        out.append("D	%d	%d	%d	%d	%s	%s	%s	%s	%d	%d	%d	%d	%d	%d	%d" % (
            e["day"], e["dow"], e["week"], e["id"], _t(e["title"], 70).upper(), e["tone"], _t(e["map"], 30).upper(), "1" if e["win"] == 1 else "0" if e["win"] == 0 else "-",
            e["sup"], e["need"], e["h"], e["u"], e["s"], e["dn"], 1 if e["id"] > seen_id else 0))
    for e in ents:
        if e["week"] != week:
            continue
        for cap, text in e["paras"]:
            out.append("G	%d	%s	%s" % (e["day"], _t(cap, 40), _t(text, 700)))
    return out


def _journal_rows(pub, feed, lang, seen_id=0):
    if not seen_id and feed:                                        # a first visit: only the newest day's lines are NEW (the launcher does the same)
        top = max((int(m.get("week") or 0), int(m.get("day") or 0)) for m in feed)
        older = [int(m.get("id") or 0) for m in feed if (int(m.get("week") or 0), int(m.get("day") or 0)) < top]
        seen_id = max(older) if older else 0
    ppl = {p["name"]: p for p in pub.get("roster", [])}
    out = []
    jr = clan_story.story_rows(feed) if feed and "card" not in feed[0] else feed     # the rows (stories + one-liners), newest first
    # an entry = 3..6 events, ONE author (two when the lead event names two), authors rotate (tools/clan_journal_entries.py); nothing is dropped
    for e in clan_journal_entries.compose_entries(jr, list(pub.get("roster", [])), seen_id)[:MAX_JOURNAL]:
        m = e["prim"]
        style = str(m.get("style") or "")
        arc = _t(m.get("arc") or m.get("thread") or "")             # read_feed: arc id (+ step) of a story arc step or of a saga thread; "thread" = a diary chain (illness, mourning: clan_continuity)
        is_arc = bool(arc)
        step = int(m.get("step") or m.get("tstep") or 1) if is_arc else 0
        head, body = e["head"], e["body"]
        kind = style.replace("arc_", "")
        if is_arc:
            tag = ARC_TAG.get(kind) or SAGA_TAG.get(style) or DIARY_TAG.get(str(arc).split("-")[0], "")
            cap = "STORY - %sDAY %s - STEP %s" % (tag + " - " if tag else "", _dow(m.get("day")), step)
        else:
            cap = "%s - DAY %s" % (CAP.get(style, "CAMP LOG") if style else "CAMP LOG", _dow(m.get("day")))
        if lang == "pl":
            cap = " - ".join(CAP_PL.get(p.strip(), p.strip().replace("DAY", "DZIEŃ").replace("STEP", "KROK")) for p in cap.split(" - "))
        tone = TONE.get(style, "") if style else MOOD_TONE.get(m.get("mood") or "", "")
        au = [ppl[n] for n in e["authors"] if n in ppl]
        first = au[0] if au else None
        who = " & ".join(p["name"] for p in au)
        out.append("J	%s	%s	%s	%s	%s	%s	%d	%s	%s	%s	%s	%d" % (e["id"], _t(cap, 60), _t(head, 90).upper(), _body(body), tone, arc, step,
                   _dow(m.get("day")), m.get("week"), _t(first.get("portrait", "") if first else "", 20), _t(who, 24), e["new"])
                   + "	0")                                         # 13th field: "more" - every event of the entry is in its body now, no L rows
    return out


STATE_WORD2 = {"en": {"hungry": "HUNGRY", "sad": "GRIEVING", "sick": "SICK", "dead": "DEAD", "injured": "HURT", "recovered": "RECOVERED", "new": "NEW MEMBER",
                      "depressed": "DEPRESSED", "shock": "SHOCK", "healthy": "HEALTHY"},
               "pl": {"hungry": "GŁODNY", "sad": "W ŻAŁOBIE", "sick": "CHORY", "dead": "MARTWY", "injured": "RANNY", "recovered": "ZDROWY", "new": "NOWY",
                      "depressed": "PRZYGNĘBIONY", "shock": "W SZOKU", "healthy": "ZDROWY"}}


def _status_rows(pub, lang):
    ppl = {p["name"]: p for p in pub.get("roster", [])}
    out = []
    for e in (pub.get("status") or [])[-4:][::-1]:
        st = e.get("state", "healthy")
        pid = (e.get("img") or {}).get(e.get("expr", "neutral"), "")
        role = (ppl.get(e["name"]) or {}).get("roleText") or e.get("role", "")
        out.append("U\t%s\t%s\t%s\t%s\t%s\t%s" % (_t(e["name"], 24), _t(str(role).upper(), 24), st, STATE_WORD2[lang].get(st, st.upper()), _t(pid, 20), _t(e.get("line", ""), 150)))
    return out


def _raid_rows(pub, last, lang, seen_day=0):
    if not seen_day and pub.get("matches"):                        # a first visit: only the newest raid is NEW
        seen_day = max(int(m.get("d", 0)) for m in pub["matches"]) - 1
    out = []
    sup = (last or {}).get("sup") or {}
    nodata = not (pub.get("matches") or []) and not any(int(v) for v in (sup.get("stock") or {}).values())      # nothing booked yet: no tiles of 5 x "NONE"
    for i, k in enumerate(clan_supply.CATS if sup.get("need") and not nodata else ()):     # no per-need split in the last result (an old / reset clan): no tiles rather than five "NONE"
        need = int((sup.get("need") or {}).get(k, 0))
        out.append("S\t%s\t%d\t%d\t%d" % (CAT_LABEL[lang][i], int((sup.get("stock") or {}).get(k, 0)), int((sup.get("days") or {}).get(k, 0)) if need else -1, need))
    loot = []
    for m in (pub.get("matches") or [])[:MAX_MATCHES]:
        cat = m.get("cat") or {}
        got = [int((cat.get("got") or {}).get(k, 0)) for k in clan_supply.CATS]
        need = [int((cat.get("need") or {}).get(k, 0)) for k in clan_supply.CATS]
        win = m.get("win")
        new = 1 if int(m.get("d", 0)) > seen_day else 0
        out.append("M\t%s\t%s\t%s\t%s\t%s\t%d\t%s\t%s" % (m.get("d"), _t(m.get("map"), 30), "-" if win is None else "1" if win else "0", m.get("sup", 0), m.get("need", 0), new,
                   " ".join(map(str, got)), " ".join(map(str, need))))
        for f in (m.get("finds") or [])[:6]:
            loot.append("T\t%s\t%s\t%s\t%s\t%d" % (m.get("d"), f.get("n", 1), _t(f.get("item", ""), 60), _icon(f.get("icon")), new))
        if not m.get("finds"):
            for k, n in (m.get("loot") or [])[:6]:
                loot.append("T\t%s\t%s\t%s\t%s\t%d" % (m.get("d"), n, _t(CH.loot_phrase(k, n, lang), 60), _icon("keepsake" if k in CH.KEEP else k), new))
    return out + loot


def stats_roster(c, mid, mapname, rows, winner):
    """The players of a finished match (daemon, on the host's 0x12): rows = [(token, name, team, left)], winner = 0 / 1 team or 2 for a draw. Adds the missing rows and the
    team / verdict of the known ones; the stats of a player come with its own report (stats_report)."""
    if not mid:
        return
    for s in STATS_SCHEMA:
        c.execute(s)
    now = __import__("time").time()
    for tok, name, team, left in rows:
        win = -1 if winner not in (0, 1) else 1 if team == winner else 0
        c.execute("INSERT INTO match_stats(mid, token, name, team, win, map, left, ts) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(mid, token) DO UPDATE SET "
                  "name=excluded.name, team=excluded.team, win=excluded.win, map=excluded.map, left=excluded.left", (str(mid), tok, _t(name, 24), int(team), win, _t(mapname, 30), 1 if left else 0, now))
    c.execute("DELETE FROM match_stats WHERE ts < ?", (now - STATS_KEEP_S,))


def stats_report(c, mid, token, name, team, counts, left):
    """One player's own award counts of the match (op 0xE2 labels: 1 kills / 2 executions / 3 revives / 4 headshots / 21 downs / 22 deaths; the client may leave 21 / 22 out)."""
    if not mid:
        return
    for s in STATS_SCHEMA:
        c.execute(s)
    cnt = dict(counts or {})

    def v(lab, always=False):
        return int(cnt.get(lab, 0)) if (lab in cnt or (cnt and always)) else -1
    now = __import__("time").time()
    c.execute("INSERT INTO match_stats(mid, token, name, team, kills, downs, deaths, revives, execs, heads, left, ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mid, token) DO UPDATE SET "
              "name=excluded.name, team=CASE WHEN excluded.team >= 0 THEN excluded.team ELSE team END, kills=excluded.kills, downs=excluded.downs, deaths=excluded.deaths, "
              "revives=excluded.revives, execs=excluded.execs, heads=excluded.heads, left=excluded.left", (str(mid), token, _t(name, 24), int(team), v(1, True), v(21), v(22), v(3, True), v(2, True), v(4, True), 1 if left else 0, now))


def stats_parts(c, mid, token, parts):
    """The parts the player earned in the match (booked by clan_finalize after the late-join bonus)."""
    try:
        c.execute("UPDATE match_stats SET parts=? WHERE mid=? AND token=?", (int(parts), str(mid), token))
    except Exception:                                               # noqa: BLE001 - no table yet = nothing recorded
        pass


MATCH_EXPR = ("neutral", "happy", "dead", "angry", "perk")        # the expressions the MATCH STATS list shows (clan13.c: award -> face); a head needs all of them
_HEADS = {}


def stats_head_pool():
    """[(model id, sex, faction)] of the grown-up heads that have every MATCH_EXPR render (clan_portrait_pool: EXPR lists what re/clan-portraits/img holds)."""
    if "pool" not in _HEADS:
        try:
            from clan_portrait_pool import POOL, EXPR
            _HEADS["pool"] = [(r[0], r[3], r[2]) for r in POOL if r[4] in ("adult", "elder") and all(e in EXPR.get(r[0], ()) for e in MATCH_EXPR)]
        except Exception:                                           # noqa: BLE001 - no pool = no heads (the client draws the plain tile)
            _HEADS["pool"] = []
    return _HEADS["pool"]


def stats_heads(rows):
    """{token: head model id} for the players of one match: a stable face per player token (same player, same face in every match and for every viewer; the sex and the head come
    from the token's hash), team 0 wears WLF heads and team 1 Seraphite ones (neutral heads fit either), no two players of the match share a head while the pool has free ones.
    The daemon knows no look per player, so this is a face for the list, not the character the player ran."""
    import zlib
    pool = stats_head_pool()
    used, out = set(), {}
    if not pool:
        return out
    for tok, team in sorted(rows):
        h = zlib.crc32(("head|" + tok).encode("utf-8")) & 0xFFFFFFFF
        sex = "f" if h & 1 else "m"
        fk = "S" if team == 1 else "W"
        cand = [m for m, sx, fc in pool if sx == sex and fc in (fk, "N") and m not in used] or [m for m, sx, fc in pool if sx == sex and m not in used] or [m for m, _, _ in pool if m not in used] or [m for m, _, _ in pool]
        own = [m for m in cand if any(fc == fk for mm, _, fc in pool if mm == m)]
        pick = own if own and (h >> 8) % 4 else cand                    # the faction's own heads 3 times in 4
        out[tok] = pick[(h >> 12) % len(pick)]
        used.add(out[tok])
    return out


def player_rank(c, token):
    """(symbol 0..9, weeks 0..999) of the player behind a daemon token: the clan row of his Steam account ("s:<id>", as daemon.clan_key) else the install token's; (0, 0) when unknown."""
    try:
        r = c.execute("SELECT steamid FROM players WHERE token=?", (token,)).fetchone()
        sid = int(r[0]) if r and r[0] else 0
        for key in (("s:%d" % sid,) if sid else ()) + (clan.token_id(token),):
            if c.execute("SELECT 1 FROM clans WHERE token_id=?", (key,)).fetchone():
                return clan.rank_of(clan.load(c, key))
    except Exception:                                               # noqa: BLE001 - the rank is decoration
        pass
    return 0, 0


def _stats_rows(c, pub, day, token):
    out = []
    m = next((x for x in (pub.get("matches") or []) if int(x.get("d", 0)) == int(day)), None)
    mid = str((m or {}).get("mid") or "")
    rows = []
    if mid:
        try:
            rows = c.execute("SELECT name, team, win, kills, downs, deaths, revives, execs, heads, parts, left, token FROM match_stats WHERE mid=? ORDER BY CASE WHEN team < 0 THEN 2 ELSE team END, "
                             "parts DESC, kills DESC, name", (mid,)).fetchall()
        except Exception:                                           # noqa: BLE001 - the table appears with the first recorded match
            rows = []
    mine = next((r[1] for r in rows if token and r[11] == token), -1)
    if mine >= 0:                                                   # the requester's own team first
        rows = sorted(rows, key=lambda r: 0 if r[1] == mine else 1)
    win = m.get("win") if m else None
    out.append("X	%d	%s	%s	%d" % (int(day), _t((m or {}).get("map"), 30), "-" if win is None else "1" if win else "0", min(len(rows), MAX_STATS)))
    heads = stats_heads([(r[11], r[1]) for r in rows[:MAX_STATS]])
    for r in rows[:MAX_STATS]:
        rk, wk = player_rank(c, r[11])                              # fields 14 / 15: the 2013 rank symbol (0..9) and the weeks survived in total (an older client ignores them)
        out.append("Q	%s	%d	%d	%d	%d	%d	%d	%d	%d	%d	%d	%d	%d	%d" % (_t(r[0] or "?", 24), r[1], 1 if token and r[11] == token else 0, r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], heads.get(r[11], 0), rk, wk))
    return out


def build(c, tid, lang="en", section=1, seen_id=0, seen_day=0, token=None):
    """The reply text of op 0xB6 for the clan `tid` ('' when it has no clan / no story / an unknown section)."""
    lang = "pl" if clan_story.PLN.norm_lang(lang) == "pl" else "en"
    if section not in (1, 2, 3, 4, 5, 6, 7):
        return ""
    row = _clan_row(c, tid)
    if not row or not row[1]:
        return ""
    camp = clan_story.read_people(c, tid, lang=lang)
    pub = CH.public(c, tid, lang) or {}
    last = _last_result(c, tid)
    try:
        cl = clan.load(c, tid)
        meta = json.loads(cl.get("meta") or "{}") if isinstance(cl.get("meta"), str) else {}
        pub["_clan"] = {"won": cl.get("runs_won", 0), "lost": cl.get("runs_lost", 0), "max": max(int(meta.get("max", 0)), len(pub.get("roster") or []))}
    except Exception:                                               # noqa: BLE001
        pass
    lines = [_header(row, camp, last, pub, lang)]
    ents = []
    if section in (2, 6):
        try:
            import clan_journal
            ents = clan_journal.entries(c, tid, lang, int(row[2]))
        except Exception:                                           # noqa: BLE001 - no journal table yet: the older rows below
            ents = []
    if section == 6:
        lines += _journal_week_rows(ents, lang, seen_id, seen_day)
    elif section == 2 and ents:
        lines += _journal_day_rows(ents, lang, seen_id)
    elif section == 1 or section == 2:
        feed = clan_story.read_feed(c, tid, 100 if section == 2 else 40, 0, lang, callbacks=(section == 2), fold=(section == 2))  # fold = mark stories / one-liners (clan_story.story_rows)
        lines += _person_rows(pub, feed, lang, camp, int(row[2])) if section == 1 else _journal_rows(pub, feed, lang, seen_id)
    elif section == 4:
        lines += _status_rows(pub, lang)
    elif section == 5:
        lines += _stats_rows(c, pub, seen_day, token)
    elif section == 7:
        lines += _end_rows(c, tid, int(row[1]))
    else:
        lines += _raid_rows(pub, last, lang, seen_day)
    return "\n".join(lines)


ROLL = 7                          # faces on the end screen's roll call
TAB = chr(9)


def _end_rows(c, tid, status):
    """Section 7 (the clan end screens, tools/ext/clanend.c): E kind(W won / L lost) shown more remembered raidsWon raidsPlayed, then R name portraitId
    per face (<= 7). Won: the survivors who walked out (the roster order, the longest in the camp first); lost: the last who died, newest last, with the
    dead portrait. Empty while the clan still lives."""
    if status not in (clan.DEAD, clan.WON):
        return []
    st = clan_story._load(c, tid)
    if not st:
        return ["E%s%s%s0%s0%s0%s0%s0" % (TAB, "W" if status == clan.WON else "L", TAB, TAB, TAB, TAB, TAB)]
    fk = "S" if st.get("fac") == clan.SERAPHITES else "W"
    people, dead = list(st.get("people") or []), list(st.get("dead") or [])
    log = CH.ch_state(st).get("log") or []
    won = sum(1 for e in log if e.get("win") is True or e.get("win") == 1)
    members = people + dead
    if status == clan.WON:
        faces = [(p["n"], CH.portrait_id(p, fk, state="h", morale=80, members=members)) for p in people[:ROLL]]
        more = max(0, len(people) - ROLL)
    else:
        faces = [(d["n"], CH.portrait_id(d, fk, state="d", members=members)) for d in dead[-ROLL:]]
        more = 0
    out = [TAB.join(["E", "W" if status == clan.WON else "L", str(len(faces)), str(more), str(len(dead)), str(won), str(len(log))])]
    out += [TAB.join(["R", _t(n, 24), _t(pid, 20)]) for n, pid in faces]
    return out
