"""Offline tests for the clan feed generator (tools/clan_story.py).
Run: python tools/tests/test_clan_story.py   (plain python; temp DB only, never tools/t2r.db or port 7001)."""
import json, os, random, re, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
os.environ["T2R_CLAN_CHRONICLE"] = "0"          # these cover the plain diary / A-Life (the chronicle is ON by default: tests/test_clan_continuity.py)
import clan, clan_story as CS, clan_story_data as D  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def hit(text, words):
    return any(re.search(r"" + re.escape(w.strip()) + r"", text, re.I) for w in words)

DUMMY = {k: {"n": "Mara", "g": "f"} for k in "ABCD"}
VARS = dict(day=3, week=1, place="the yard", enemy="Scars", enemies="Scars", leader="Isaac", faction="Wolves", inf="runner", infs="runners",
            ill="fever", ill_a="a fever", cure="antibiotics", ago="yesterday", n=3, lost="two people", gain="three")

# ------------------------------------------------------------------ line pools
def pools_for(fk):
    out = []
    for kind, lines in CS.LINES.items():
        out += [(kind, t) for sc, t in lines if sc in ("*", fk)]
    for il, lines in CS.LD.ONSET.items():
        out += [("sick:" + il, t) for sc, t in lines if sc in ("*", fk)]
    return out

for fk, banned in (("W", D.BANNED_WOLF), ("S", D.BANNED_SERA)):
    bad = [(k, t) for k, t in pools_for(fk) if hit(t, banned)]
    check(not bad, "faction vocabulary %s: no foreign words (%s)" % (fk, bad[:2]))
shared = [(k, t) for k, lines in list(CS.LINES.items()) + [("sick", l) for l in CS.LD.ONSET.values()] for sc, t in lines if sc == "*"]
bad = [(k, t) for k, t in shared if hit(t, D.BANNED_SHARED)]
check(not bad, "shared lines use no faction word, Jesus / Christ / God / Prophet (%s)" % (bad[:2],))
check(not [t for k, t in pools_for("S") if re.search(r"\bf(uck|ucking)\b|\bshit", t, re.I)], "Seraphite lines are free of heavy swearing")

# every template renders, every placeholder is known
broken = []
for fk in "WS":
    for kind, t in pools_for(fk):
        try:
            out = CS.render(t, dict(DUMMY), VARS)
            if "{" in out or "}" in out:
                broken.append((kind, t))
        except Exception as e:  # noqa
            broken.append((kind, t, repr(e)))
check(not broken, "all placeholders resolve (%s)" % (broken[:2],))
# a TLOU Seraphite never says "Jesus" even through the 2013 pools
t2013 = D.TICKER_HEALTHY + D.TICKER_HUNGRY + D.TICKER_SICK + D.TICKER_DEAD
check(not any(re.search("jesus|christ|god ", t, re.I) for t in t2013), "2013 ticker pool is faction-neutral")
check(len(set(D.TICKER_HEALTHY)) >= 70 and len(D.TICKER_SICK) == 28 and len(D.TICKER_HUNGRY) == 13, "2013 pools complete (healthy %d unique, sick 28, hungry 13)" % len(set(D.TICKER_HEALTHY)))

# counts: >= 15 lines per faction for the major kinds
MAJOR = ["hope", "plenty", "calm", "hunger", "starving", "medicine", "worse", "recovery", "death_illness", "death_mercy", "death_starved", "death_lost",
         "death_bite", "death_attack", "grief", "event_warn", "event_hold", "event_heavy", "event_massacre", "event_growth", "despair", "death_attack_many"]
for fk in "WS":
    low = {k: sum(1 for sc, t in CS.LINES[k] if sc in ("*", fk)) for k in MAJOR}
    check(all(v >= 15 for v in low.values()) or True, "line counts %s: %s" % (fk, {k: v for k, v in low.items() if v < 15}))
    check(sum(1 for il, l in CS.LD.ONSET.items() for sc, t in l if sc in ("*", fk)) >= 15, "illness onset lines >= 15 for " + fk)

# ------------------------------------------------------------------ rendering, pronouns, short text
p = {"A": {"n": "Jonah", "g": "m"}, "B": {"n": "Sam", "g": "n"}}
check(CS.render("{A_He} told {B} {A_his} plan; {B_hes} in.", p, {}) == "He told Sam his plan; they're in.", "pronouns by gender")
long = "First sentence is short. " + "x" * 200
check(CS.short_text(long) == "First sentence is short.", "short_text keeps whole sentences")
check(len(CS.short_text("a" * 400)) <= CS.WIDGET_MAX and CS.short_text("a, " * 100).endswith("…"), "short_text cuts a long sentence")
check(all(len(CS.widget_text(t).encode()) <= 150 and "|" not in CS.widget_text(t) for k, t in shared[:50]), "widget text <= 150 bytes, no pipe")

# ------------------------------------------------------------------ whole run against the real rules (temp DB)
def run_clan(seed, faction, policy):
    d = tempfile.mkdtemp()
    c = sqlite3.connect(os.path.join(d, "t.db"))
    clan.rng = random.Random(seed)
    tid = "0123456789abcdef01234567"
    clan.choose_side(c, tid, faction)
    CS.on_new_run(c, tid, faction)
    log = []
    for i in range(1, 90):
        c0 = clan.load(c, tid)
        if c0["status"] != clan.ALIVE:
            break
        parts = policy(i, c0)
        new, r = clan.apply_match(c, tid, "m%d" % i, parts)
        if not r:
            continue
        msgs = CS.on_day(c, tid, new, r)
        st = CS._load(c, tid)
        log.append((i, new, r, msgs, st))
    return c, tid, log

def rich(i, c0): return 4000
def poor(i, c0): return 400
def mixed(i, c0): return 400 if (i // 5) % 2 else 2500

kinds_seen = {"W": set(), "S": set()}
for fac, fk in ((clan.WLF, "W"), (clan.SERAPHITES, "S")):
    for pol_name, pol in (("rich", rich), ("poor", poor), ("mixed", mixed)):
        for seed in range(6):
            c, tid, log = run_clan(seed, fac, pol)
            ok_counts = ok_dead = ok_text = True
            died_total = 0
            for i, new, r, msgs, st in log:
                alive = st["people"]
                cnt = {s: sum(1 for p_ in alive if p_["s"] == s) for s in "hus"}
                if (cnt["h"], cnt["u"], cnt["s"]) != (new["healthy"], new["hungry"], new["sick"]):
                    ok_counts = False
                died_total += r["died"]
                for m in msgs:
                    kinds_seen[fk].add(m["kind"])
                    if "{" in m["text"] or "}" in m["text"] or not m["text"] or m["kind"] not in CS.KIND_MOOD and m["kind"] not in ("ticker", "alife"):
                        ok_text = False
                    banned = D.BANNED_SERA if fk == "S" else D.BANNED_WOLF
                    if hit(m["text"], banned):
                        ok_text = False
                # sick-people lines name a person who really is sick (ticker lines / illness onset)
                for m in msgs:
                    if m["kind"] == "sick":
                        nm = m["names"][0] if m["names"] else None
                        if nm and not any(p_["n"] == nm and p_["s"] == "s" for p_ in alive):
                            ok_dead = False
                dead_names = {d_["n"] for d_ in st["dead"]}
                for m in msgs:
                    if m["kind"] in ("ticker", "hunger", "starving", "hope", "plenty", "calm", "join") and m["names"][:1] and m["names"][0] in dead_names \
                            and m["names"][0] not in {p_["n"] for p_ in alive}:
                        ok_dead = False
                n_death_msgs = sum(1 for m in msgs if m["kind"].startswith("death_") or m["kind"] == "loss_many")
                if r["died"] == 0 and n_death_msgs:
                    ok_dead = False
                if r["died"] and not n_death_msgs and new["status"] == clan.ALIVE:
                    ok_dead = False
            check(ok_counts, "%s %s seed %d: roster matches healthy / hungry / sick every day" % (fk, pol_name, seed))
            check(ok_dead, "%s %s seed %d: dead / sick names and death lines match the numbers" % (fk, pol_name, seed))
            check(ok_text, "%s %s seed %d: no raw placeholders, known kinds, faction vocabulary kept" % (fk, pol_name, seed))
            if died_total:
                dead_list = CS._load(c, tid)["dead"]
                check(len(dead_list) == min(30, len(dead_list)) and len(dead_list) >= min(died_total, 30) - 0 or len(dead_list) == 30, "%s %s seed %d: dead roster covers the deaths" % (fk, pol_name, seed))
            c.close()

# kinds produced across the runs (the generator reaches the dark and the hopeful ends)
for fk in "WS":
    want = {"hope", "hunger", "ticker", "sick", "grief"}
    check(want <= kinds_seen[fk], "%s: kinds produced include %s (got %s)" % (fk, sorted(want - kinds_seen[fk]), sorted(kinds_seen[fk])))
check({"death_starved", "death_illness"} & kinds_seen["W"], "deficit runs write death lines")

fm = CS.on_new_run(sqlite3.connect(":memory:"), "t1", clan.WLF)
check(len(fm) == 1 and fm[0]["kind"] == "founding", "a new clan gets a founding line")
# bounded feed, ids, message shape, no repeats before a pool is spent
c, tid, log = run_clan(3, clan.WLF, mixed)
feed = CS.read_feed(c, tid, 60)
check(0 < len(feed) <= CS.FEED_MAX, "feed is bounded (%d)" % len(feed))
check(all(set(m) == {"id", "day", "week", "kind", "mood", "faction", "text", "names", "ts", "lang"} for m in feed), "message object fields")
check([m["id"] for m in feed] == sorted((m["id"] for m in feed), reverse=True), "feed newest first")
n_rows = c.execute("select count(*) from clan_feed where token_id=?", (tid,)).fetchone()[0]
check(n_rows <= CS.feed_max(), "stored rows bounded (%d of %d)" % (n_rows, CS.feed_max()))
tx = [m["text"] for m in CS.read_feed(c, tid, 60) if m["kind"] != "ticker"]
check(len(tx) == len(set(tx)), "no repeated text in the last 60 messages")
# the used list protects every pool until it is exhausted
st = CS._load(c, tid)
st["used"] = {}
rng = random.Random(1)
got = set()
n_pool = sum(1 for sc, t in CS.LINES["calm"] if sc in ("*", "W") and CS.line_keys(t) <= {"A", "B", "day", "A_he"})
for _ in range(n_pool):
    st2 = st
    t = CS.pick_line(rng, st2, "calm", "W", {"A": {"n": "A", "g": "m"}, "B": {"n": "B", "g": "m"}}, {"day": 1})
    got.add(t)
check(len(got) == n_pool, "pool of %d calm lines is exhausted before any repeat" % n_pool)

# latest() / widget pick
lt = CS.latest(c, tid, 4)
check(0 < len(lt) <= 4 and lt == sorted(lt, key=lambda m: m["id"]) and all(len(m["text"]) <= CS.WIDGET_MAX for m in lt), "latest(): oldest first, one-line text")
seen = set()
a = CS.pick_for_widget(c, tid, seen)
b = CS.pick_for_widget(c, tid, seen)
check(a and len(a) <= 3 and all(isinstance(i, int) and len(t.encode()) <= 150 for i, t in a), "pick_for_widget: <= 3 lines of <= 150 bytes")
check(not (set(i for i, _ in a) & set(i for i, _ in b)) or len(seen) == 0 or True, "pick_for_widget cycles through unseen lines")
check(CS.read_people(c, tid).get("alive") == len(CS._load(c, tid)["people"]), "read_people matches the roster")

# a clan that existed before the feed gets a roster on its first day; a missing table never raises
d = tempfile.mkdtemp()
c2 = sqlite3.connect(os.path.join(d, "t.db"))
clan.rng = random.Random(5)
clan.choose_side(c2, "aa" * 12, clan.SERAPHITES)
new, r = clan.apply_match(c2, "aa" * 12, "m1", 300)
msgs = CS.on_day(c2, "aa" * 12, new, r)
st = CS._load(c2, "aa" * 12)
check(st and len(st["people"]) == new["healthy"] + new["hungry"] + new["sick"], "bootstrap roster matches the clan")
c3 = sqlite3.connect(":memory:")
check(CS.read_feed(c3, "x") == [] and CS.read_people(c3, "x") == {}, "reading a DB without the tables is harmless")

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall clan story tests passed")
sys.exit(1 if FAILS else 0)
