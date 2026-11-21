"""Achievements (tools/achievements.py + the daemon's 0xA9 / 0xAA ops and clan-day booking). Temp DB only.
Run: python tools/tests/test_achievements.py"""
import os, sys, struct, tempfile, sqlite3
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
sys.path.insert(0, TOOLS)
import achievements as A  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


# ---- the table ----
check(40 <= len(A.ACH) <= 80, "table size %d" % len(A.ACH))
check(all(a["title"] and a["desc"] and a["group"] in ("melee", "weapon", "skill", "stats", "clan", "secret") for a in A.ACH), "every entry has title / desc / group")
check(all(a["title"] == a["title"].upper() for a in A.ACH), "titles are upper case")
check(A.BY_ID["se_crowbar"]["title"] == "I'M A FREE MAN" and A.BY_ID["se_crowbar"]["goal"] == 50, "I'M A FREE MAN = 50 crowbar SEs (15 was one or two matches)")
check(A.BY_ID["se_hammer"]["title"] == "HAMMER TIME", "user example: HAMMER TIME")
for need in ("grave_1", "weeks_12", "rank_1", "rank_5", "rank_10"):
    check(need in A.BY_ID, "user ask: %s exists" % need)

# ---- pure booking on an in-memory db ----
c = sqlite3.connect(":memory:")
K = "s:1"
done = {}
got = A.book_match(c, K, {A.L_DOWNS: 3, A.L_SE_CROWBAR: 2, A.L_EXECS: 2}, done, win=True)
check("raid_1" in got, "first match unlocks FIRST RAID")
check(A.counters(c, K)[A.L_SE_CROWBAR] == 2, "crowbar SE counted")
got = A.book_match(c, K, {A.L_DOWNS: 3, A.L_SE_CROWBAR: 2, A.L_EXECS: 2}, done, win=True, first=False)
check(got == [] and A.counters(c, K)[A.L_SE_CROWBAR] == 2 and A.counters(c, K)[A.D_MATCHES] == 1, "re-send of the same match counts nothing")
got = A.book_match(c, K, {A.L_DOWNS: 3, A.L_SE_CROWBAR: 3, A.L_EXECS: 3, A.L_DODGES: 9}, done, win=True, first=False)
check(A.counters(c, K)[A.L_SE_CROWBAR] == 3, "a later report of the same match adds only the difference")
check("dodge_5" not in got, "9 dodges in one match -> no NOT EVEN CLOSE (10 needed)")
got = A.book_match(c, K, {A.L_DODGES: 10}, {}, win=False)
check("dodge_5" in got, "10 dodges in one match -> NOT EVEN CLOSE")
for i in range(9):
    got = A.book_match(c, K, {A.L_SE_CROWBAR: 5, A.L_EXECS: 5, A.L_DOWNS: 5}, {}, win=False)
check(A.counters(c, K)[A.L_SE_CROWBAR] == 48 and "se_crowbar" not in got, "48 crowbar SEs -> not yet")
got = A.book_match(c, K, {A.L_SE_CROWBAR: 2, A.L_EXECS: 2, A.L_DOWNS: 2}, {}, win=False)
check(A.counters(c, K)[A.L_SE_CROWBAR] == 50 and "se_crowbar" in got, "50 crowbar SEs over 11 matches -> I'M A FREE MAN")
# anti-cheat-ish sanitising
s = A.sanitize({A.L_SE_HAMMER: 40, A.L_EXECS: 4, A.L_MOLOTOV: 9, A.L_DOWNS: 2, 300: 5, A.L_DODGES: 999})
check(s.get(A.L_SE_HAMMER, 0) <= 4, "SE weapon split never above the executions (%s)" % s.get(A.L_SE_HAMMER))
check(s.get(A.L_MOLOTOV) == 2, "weapon-kind downs never above the downs")
check(300 not in s and s[A.L_DODGES] == A.MAX_PER_MATCH, "unknown labels dropped, per-match cap")
# match tests
got = A.book_match(c, K, {A.L_DOWNS: 6}, {}, win=True)
check("flawless" in got, "win, 6 downs, no deaths -> UNTOUCHABLE")
got = A.book_match(c, K, {A.L_DOWNS: 9, A.L_MELEE_DOWN: 9}, {}, win=True)
check("melee_only" not in got, "9 melee downs in a win -> no WHO NEEDS GUNS (10 needed)")
got = A.book_match(c, K, {A.L_DOWNS: 10, A.L_MELEE_DOWN: 10}, {}, win=True)
check("melee_only" in got, "10 downs, all melee, in a win -> WHO NEEDS GUNS")
got = A.book_match(c, K, {A.L_REVIVES: 3}, {}, win=True)
check("pacifist" in got, "win with no downs and 3 revives -> PACIFIST")
got = A.book_match(c, K, {A.L_REVIVES: 3}, {}, win=True, left=True)
check(A.counters(c, K)[A.D_WINS] == 5, "a left match books no win (wins %d)" % A.counters(c, K)[A.D_WINS])
got = A.book_match(c, K, {}, {}, win=True, late=True)
check("late_win" in got, "late join + win -> FASHIONABLY LATE")
got = A.book_match(c, K, {A.L_OWN_MOLOTOV: 1, A.L_DOWNS: 0}, {}, win=False)
check("darwin" in got, "own molotov -> DARWIN AWARD")
got = A.book_match(c, K, {A.L_COMEBACK: 1}, {}, win=False)
check("comeback" not in got, "Comeback Bonus in a lost match -> no COMEBACK KID")
got = A.book_match(c, K, {A.L_COMEBACK: 1}, {}, win=None)
check("comeback" not in got, "Comeback Bonus, unknown result -> no COMEBACK KID")
got = A.book_match(c, K, {}, {}, win=True)
check("comeback" not in got, "a win with no Comeback Bonus -> no COMEBACK KID")
got = A.book_match(c, K, {A.L_COMEBACK: 1}, {}, win=True)
check("comeback" in got, "Comeback Bonus + won -> COMEBACK KID")

# ---- clan days ----
alive = {"faction": 1, "status": 1, "day": 10, "healthy": 20, "hungry": 0, "sick": 0, "days_total": 6}
got = A.book_clan(c, K, alive, dict(alive, days_total=7), {"died": 0})
check(got == ["rank_1"], "7 lifetime days = rank 1 (%s)" % got)
got = A.book_clan(c, K, alive, alive, {"died": 2})
check("grave_1" in got, "first clan death -> FIRST GRAVE")
got = A.book_clan(c, K, alive, dict(alive, status=3, day=83, days_total=84), {})
check("weeks_12" in got and "wlf_12" in got and "rank_10" in got and "both_12" not in got, "12 weeks as WLF -> TWELVE WEEKS, WOLF PACK, rank 12 (%s)" % got)
got = A.book_clan(c, K, dict(alive, faction=2), dict(alive, faction=2, status=3, days_total=170), {})
check("sera_12" in got and "both_12" in got and "rank_10" not in got and "rank_5" not in got, "12 weeks as Seraphites -> THE PROPHET PROVIDES + BOTH SIDES NOW (%s)" % got)
got = A.book_clan(c, K, alive, dict(alive, status=2, healthy=0), {"died": 5})
check("wiped" in got, "clan lost -> NOTHING LEFT")
got = A.book_clan(c, K, alive, dict(alive, healthy=80, hungry=15, sick=5), {"evk": 2, "evt": 3})
check("haven" in got and "hold_line" in got, "100 survivors + top-tier attack -> SAFE HAVEN, HOLD THE LINE")

# ---- wire text ----
txt = A.wire_text(c, K, 24)
lines = txt.strip().split("\n")
check(lines[0].startswith("ACH ") and len(lines) == len(A.ACH) + 1, "wire text: header + one line per achievement")
row = {l.split("|")[0]: l.split("|") for l in lines[1:]}
check(row["se_crowbar"][2] != "0" and row["se_crowbar"][3] == "50", "unlocked row carries its time + full progress")
check(row["reaper"][6] == "?" and row["reaper"][7] == "Hidden achievement", "locked hidden achievement masked")
check(row["darwin"][6] == "DARWIN AWARD", "unlocked hidden achievement shown")
check(row["dodge_50"][3] == "19" and row["dodge_50"][4] == "250", "progress n / goal on a locked counter")
check(row["rank_25"][3] == "24", "rank progress from the rank passed in")
pub = A.public_rows(c, K)
check(len(pub) == len(A.ACH) and pub[0]["id"] == "se_crowbar", "public rows for the website")

# ---- the daemon: both report orders, re-sends, side choice ----
import daemon  # noqa: E402
TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
TOK2 = "54324e3a" + "426f62" + "00" * 13 + "0123456789abcdef76543210"
with daemon._dblock, daemon.dbc() as cc:
    for t in (TOK, TOK2):
        try:
            cc.execute("INSERT OR IGNORE INTO players (token) VALUES (?)", (t,))
        except Exception as e:
            print("note: players insert", e)
daemon.clan_side(TOK, 1)
daemon.clan_side(TOK2, 2)


def a9(tok, labs):
    pl = tok.encode() + struct.pack("<IB", 1, len(labs)) + b"".join(struct.pack("<BH", k, v) for k, v in labs.items())
    return daemon.ach_report_op(pl)


def unl(tok):
    with daemon._dblock, daemon.dbc() as cc:
        return A.unlocked(cc, daemon.clan_key(cc, tok))


def cnt(tok):
    with daemon._dblock, daemon.dbc() as cc:
        return A.counters(cc, daemon.clan_key(cc, tok))


check("side" in unl(TOK), "clan_side -> PICK A SIDE")
# order 1: 0xE2 first, then 0xA9
daemon.clan_match_started([TOK, TOK2], "m1")
daemon.clan_report(TOK, 300, 2, {1: 4, 2: 3})
rep = a9(TOK, {64: 3, 7: 3, 76: 2})
check(rep is not None and b"ACH " in rep, "0xA9 answered with the achievement text")
check(cnt(TOK).get(A.L_SE_CROWBAR) == 3 and cnt(TOK).get(A.D_MATCHES) == 1, "0xA9 after the day: booked on top (%s)" % cnt(TOK))
a9(TOK, {64: 3, 7: 3, 76: 2})
check(cnt(TOK).get(A.L_SE_CROWBAR) == 3 and cnt(TOK).get(A.L_DODGES) == 2, "re-sent 0xA9 counts nothing")
# order 2: 0xA9 first (held), then 0xE2
a9(TOK2, {65: 2, 7: 2, 1: 99})
check(cnt(TOK2).get(A.L_SE_HAMMER) is None, "0xA9 before the day is held")
daemon.clan_report(TOK2, 200, 2, {1: 2, 2: 2})
c2 = cnt(TOK2)
check(c2.get(A.L_SE_HAMMER) == 2 and c2.get(A.L_DOWNS) == 2, "held 0xA9 booked with the day; label 1 from the clamped 0xE2 only (%s)" % c2)
check("raid_1" in unl(TOK2), "FIRST RAID via the daemon")
# read op
rr = daemon.ach_read_op(TOK.encode())
check(rr is not None and b"I'M A FREE MAN" in rr, "0xAA read returns the table")
check(rr is not None and rr.rstrip(b"\n").endswith(b"\nLIVE 1"), "the table ends with LIVE 1 (this daemon takes op 0xAB)")

# ---- live unlocks (op 0xAB, shown the moment they are earned) ----
d2 = {}
c3 = sqlite3.connect(":memory:")
got = A.book_live(c3, "s:9", {A.L_BOW_TELL: 1, A.L_DODGES: 10, A.L_DOWNS: 4, 22: 3, 23: 9}, d2)
check("bow_tell" in got and "dodge_5" in got, "book_live: a lifetime goal and a one-match count unlock at once (%s)" % got)
check(A.counters(c3, "s:9").get(22) is None and A.counters(c3, "s:9").get(A.D_MATCHES) is None, "book_live: no 0xE2-only label, no match counter")
check(not any(x in got for x in ("flawless", "pacifist", "raid_1")), "book_live: no win / match-end test")
A.book_live(c3, "s:9", {A.L_BOW_TELL: 1, A.L_DODGES: 10, A.L_DOWNS: 4}, d2)
check(A.counters(c3, "s:9")[A.L_DODGES] == 10, "book_live re-sent counts nothing")
got = A.book_match(c3, "s:9", {A.L_DODGES: 12, A.L_DOWNS: 4}, d2, win=True)
check(A.counters(c3, "s:9")[A.L_DODGES] == 12 and A.counters(c3, "s:9")[A.D_MATCHES] == 1 and "raid_1" in got, "match end books on top of the live reports")
A.settle(c3, "s:9", {A.L_DOWNS: 3}, d2, (A.L_DOWNS,))
check(A.counters(c3, "s:9")[A.L_DOWNS] == 3 and d2[A.L_DOWNS] == 3, "settle: a live count above the clamped report is taken back")
rules = {r[0]: r for r in A.live_rules()}
check(rules["se_crowbar"][1:] == ("count", A.L_SE_CROWBAR, 50) and rules["dodge_5"][1:] == ("match", A.L_DODGES, 10) and rules["melee_all"][1] == "allse",
      "live rules: counters, one-match count, all melee weapons")
check(not any(r in rules for r in ("raid_1", "streak_10", "bottle_50", "flawless", "rank_1", "grave_1")), "live rules: nothing the match end / clan decides")
check(open(os.path.join(TOOLS, "ext", "ach_live.h"), encoding="utf-8").read() == A.ext_header(),
      "tools/ext/ach_live.h is current (python tools/achievements.py --ext-header)")


def ab(tok, labs):
    return daemon.ach_live_op(tok.encode() + struct.pack("<B", len(labs)) + b"".join(struct.pack("<BH", k, v) for k, v in labs.items()))


daemon.clan_match_started([TOK, TOK2], "m2")
r = ab(TOK, {75: 1, 1: 5})
check(r is not None and r[2] == 0xAB and "bow_tell" in unl(TOK), "op 0xAB books in the match and answers 0xAB with the table")
daemon.ACH_LIVE_AT.clear()
cdown = cnt(TOK).get(A.L_DOWNS)
daemon.clan_report(TOK, 300, 2, {1: 2, 2: 1})
check(cnt(TOK).get(A.L_DOWNS) == cdown - 5 + 2, "the day: the clamped 0xE2 downs replace the live ones (%s -> %s)" % (cdown, cnt(TOK).get(A.L_DOWNS)))
r = ab(TOK, {74: 1})
check(r is not None and "darwin" not in unl(TOK), "op 0xAB after the day is booked: the table only")

# ---- Polish: every achievement has ach.<id>.title / .desc (tools/loc/pl, achieve_ui.c aui_ach), with the daemon's numbers ----
import re  # noqa: E402
sys.path.insert(0, os.path.join(TOOLS, "loc"))
import locdata  # noqa: E402
PL = {e[1]: e[2] for e in locdata.load("pl")}
for a in A.ACH:
    t, d = PL.get("ach.%s.title" % a["id"]), PL.get("ach.%s.desc" % a["id"])
    check(bool(t) and bool(d), "pl title + desc for %s" % a["id"])
    if d:
        nums = lambda s: sorted(re.findall(r"\d+", s.replace(",", "").replace("2x4", "")))  # noqa: E731
        check(nums(d) == nums(a["desc"]), "pl desc numbers of %s match the goal (%s vs %s)" % (a["id"], nums(d), nums(a["desc"])))
for k in ("ACHIEVEMENTS", "MELEE MASTERY", "WEAPON FEATS", "MILESTONES", "HIDDEN", "UNLOCKED", "LOCKED", "Unlocked Achievement: %s", "NOV"):
    check(k in PL, "pl page text %r" % k)

print("\nall passed" if not FAILS else "\n%d FAILED" % len(FAILS))
sys.exit(1 if FAILS else 0)
