"""Progression consistency audit (re/progression-consistency-1019.md): randomized clan days on a SYNTHETIC in-memory DB (never the live
one) with invariants (no negative members, day +1 at most, mission left 0..3, progress >= 0, weeks_total, boosters 0..99, story roster = clan,
feed ids / days in order), the match tag that tells a new result from the old one when a day does not count, the ext's mission counters
and the daemon's second-report guard.   Run: python tools/tests/test_clan_integrity.py"""
import os, random, re, socket, sqlite3, struct, sys, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import clan, clan_story  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

# ------------------------------------------------------------------ randomized invariants
bad = {}
def note(k, v):
    bad.setdefault(k, []).append(v)

days_run = 0
for seed in range(120):
    rnd = random.Random(seed)
    clan.rng = random.Random(seed)
    c = sqlite3.connect(":memory:")
    tid = "sim%d" % seed
    clan.choose_side(c, tid, 1 + seed % 2)
    clan_story.on_new_run(c, tid, 1 + seed % 2)
    prev_day, prev_tag, n_match = 0, clan.match_tag(""), 0
    for i in range(160):
        cl = clan.load(c, tid)
        if cl["status"] != clan.ALIVE:
            break
        if rnd.random() < 0.7:
            clan.mission_choose(c, tid, rnd.choice([0, 1, 2, 3, 4, 5, 6, 7]))
        n_match += 1
        counts = {k: rnd.randint(0, 30) for k in rnd.sample(range(1, 7), rnd.randint(0, 4))}
        new, r = clan.apply_match(c, tid, "m%d" % n_match, rnd.choice([0, 0, 200, 1000, 3000, 8000]), left_early=rnd.random() < .15, counts=counts,
                                  mult=rnd.choice([1.0, 1.0, 1.0, 1.5, 2.0, 3.0]), forgive=rnd.random() < .1, bottles=rnd.choice([0, 0, 2]))
        days_run += 1
        if r is None:
            note("no result", (seed, i)); continue
        clan_story.on_day(c, tid, new, r)
        n = new["healthy"] + new["hungry"] + new["sick"]
        if min(new["healthy"], new["hungry"], new["sick"]) < 0 or n > clan.MAX_CLAN:
            note("members", (seed, i, n))
        if not 0 <= new["day"] - prev_day <= 1:
            note("day step", (prev_day, new["day"]))
        prev_day = new["day"]
        if new["status"] == clan.ALIVE and n <= 0:
            note("alive with nobody", seed)
        m = clan.meta_of(new).get("m")
        if m and (m["left"] < 0 or m["left"] > 3 or m["prog"] < 0):
            note("mission", m)
        if new["weeks_total"] != new["day"] // 7:
            note("weeks_total", (new["weeks_total"], new["day"]))
        if clan.meta_of(new).get("sh", 0) > new["sick"]:
            note("sick+hungry > sick", seed)
        tag = clan.match_tag(new["last_mid"])
        if tag == prev_tag or tag <= 0:
            note("match tag did not change", (seed, i))
        prev_tag = tag
        if "lmh=%d" % tag not in clan.state_text(new):
            note("lmh missing", seed)
        st = clan_story._load(c, tid)
        if st is None or len(st["people"]) != n:
            note("story roster != clan", (seed, i, None if st is None else len(st["people"]), n))
        bc = clan.booster_counts(c, tid)
        if min(bc.values()) < 0 or max(bc.values()) > clan.BOOSTER_MAX:
            note("boosters", bc)
    feed = [(x[0], x[1]) for x in c.execute("SELECT id, day FROM clan_feed WHERE token_id=? ORDER BY id", (tid,))]
    if any(b[0] <= a[0] or b[1] < a[1] for a, b in zip(feed, feed[1:])):
        note("feed order", seed)
check(days_run > 3000 and not bad, "randomized days (%d) keep every invariant %s" % (days_run, {k: (len(v), v[:2]) for k, v in bad.items()}))

# the match tag changes on a day that does not count (idle, x2.0): the client's lday stays the same
clan.rng = random.Random(1)
c = sqlite3.connect(":memory:")
clan.choose_side(c, "t", 1)
a, ra = clan.apply_match(c, "t", "idle1", 0)
b, rb = clan.apply_match(c, "t", "idle2", 0)
check(ra["counted"] == 0 and rb["counted"] == 0 and a["day"] == b["day"] == 0, "idle matches do not count as days")
check(clan.match_tag("idle1") != clan.match_tag("idle2") and clan.match_tag("") == 0, "...but each has its own match tag (post-match page waits for the NEW one)")
check(" lday=0 " in clan.state_text(b) and " lmh=%d " % clan.match_tag("idle2") in clan.state_text(b), "state_text carries the last match's tag: " + clan.state_text(b))

# ------------------------------------------------------------------ the ext counts the missions in their own counters
ext = open(os.path.join(TOOLS, "ext", "t2r-ext.c"), "rb").read().decode("latin1")
check("g_mis_cnt[id]++" in ext and "if (g_mis_cnt[id] > 0)" in ext and "g_pm_tally[i].label, MIS[id].label" not in ext,
      "ext: the 0xE2 tail comes from g_mis_cnt (the 12-row tally merged labels in a long match)")
check('"Special Execution"' in ext.split("static void mis_book")[1].split("}")[0], "ext: a Special Execution (every E execution) counts for the Executions mission")
check("memset(g_mis_cnt, 0, sizeof g_mis_cnt)" in ext, "ext: the counters reset with the match")
check("c->lmh != g_pm.lmh0" in ext and '"lmh"' in ext, "ext: pm_ready compares the match tag, not only lday")

# ------------------------------------------------------------------ daemon: a second report of a booked match changes nothing
tmp = tempfile.mkdtemp()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_CLAN_GRACE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)
TOK = "54324e3a" + "4d6973" + "00" * 13 + "112233445566778899aabbcc"
with daemon.dbc() as db:
    cols = [r[1] for r in db.execute("PRAGMA table_info(players)")]
    db.execute("INSERT INTO players(token) VALUES(?)", (TOK,))
def parts_n():
    with daemon.dbc() as db:
        return db.execute("SELECT parts_total, parts_n FROM players WHERE token=?", (TOK,)).fetchone()
with daemon._dblock, daemon.dbc() as db:
    clan.choose_side(db, clan.token_id(TOK), clan.WLF)
daemon.clan_match_started([TOK], "z1")
daemon.CLAN_PENDING[TOK] = ("z1", 900, 2, {})
daemon.clan_finalize(TOK)
once = parts_n()
daemon.CLAN_PENDING[TOK] = ("z1", 900, 2, {})              # the same report again (replayed snapshot / retry)
daemon.clan_finalize(TOK)
check(once == (900, 1) and parts_n() == once, "daemon: a second report of a booked match books no parts record again: %s -> %s" % (once, parts_n()))
with daemon.dbc() as db:
    check(clan.load(db, clan.token_id(TOK))["day"] == 1, "daemon: ...and no second day")

print()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
