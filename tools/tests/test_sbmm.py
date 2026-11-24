"""Team balance by K/D (one-sided matches): player_skill rates an account by its smoothed K/D over the last
SKILL_MATCHES matches (mapped onto the old 0..1 scale), the split pairs strong with weak, and a lone joiner of an even match takes the weaker team.
Run: python tools/tests/test_sbmm.py   (temp DB, no sockets)."""
import os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)
def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Ace", "Bee", "Cat", "Dog", "Eel", "Fox", "Gnu", "Hen"]
T = [tok(n) for n in NAMES]
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8",
                  T2R_MIN_PLAYERS="2", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0", T2R_DB=os.path.join(tmp, "t2r.db"))
os.chdir(tmp)
import daemon, clan_ingame  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "t2r.db"); daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.evt = lambda *a, **k: None
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
LOGS = []
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))

# 1. the mapping: K/D 1.0 = SKILL_NEW, higher K/D = higher rating
check(abs(daemon.skill_of_kd(0, 0) - daemon.SKILL_NEW) < 1e-9, "no kills / deaths = the new-player rating %.3f" % daemon.SKILL_NEW)
check(abs(daemon.skill_of_kd(30, 10) - (daemon.SKILL_A + daemon.SKILL_B * 2.0)) < 1e-9, "30 kills 10 deaths = K/D 2.0 on the scale")
check(daemon.skill_of_kd(5, 40) < daemon.SKILL_NEW < daemon.skill_of_kd(40, 5), "weak < new < strong")

# 2. player_skill from match_stats: one Steam account with two installs adds up; the cache answers the second call
with daemon._dblock, daemon.dbc() as c:
    c.execute(clan_ingame.STATS_SCHEMA if isinstance(clan_ingame.STATS_SCHEMA, str) else clan_ingame.STATS_SCHEMA[0])
    cols = [r[1] for r in c.execute("PRAGMA table_info(players)").fetchall()]
    if "steamid" not in cols:
        c.execute("ALTER TABLE players ADD COLUMN steamid INTEGER")
    alt = tok("AceAlt")
    for i, t in enumerate(T + [alt]):
        c.execute("INSERT OR IGNORE INTO players(token) VALUES(?)", (t,))
    c.execute("UPDATE players SET steamid=777 WHERE token IN (?, ?)", (T[0], alt))
    now = time.time()
    KD = {T[0]: (12, 3), alt: (12, 3), T[1]: (11, 4), T[2]: (3, 12), T[3]: (4, 11), T[4]: (7, 7), T[5]: (7, 7), T[6]: (6, 8), T[7]: (8, 6)}
    for t, (k, d) in KD.items():
        for m in range(5):
            c.execute("INSERT INTO match_stats(mid, token, name, team, kills, deaths, ts) VALUES(?,?,?,?,?,?,?)", ("m%d" % m, t, "x", 0, k, d, now - 100 * m))
    c.execute("INSERT INTO match_stats(mid, token, name, team, kills, deaths, ts) VALUES('nostats', ?, 'x', 0, -1, -1, ?)", (T[2], now))
daemon._skill_cache.clear()
sk = daemon.player_skill(T)
exp_ace = daemon.skill_of_kd(120, 30)
check(abs(sk[T[0]] - exp_ace) < 1e-9, "Ace's two installs add up (%.3f, expected %.3f)" % (sk[T[0]], exp_ace))
check(abs(sk[T[2]] - daemon.skill_of_kd(15, 60)) < 1e-9, "a match without kill stats (-1) is skipped")
check(sk[T[0]] > sk[T[1]] > sk[T[4]] > sk[T[3]] > sk[T[2]], "order follows K/D")
unknown = tok("Nobody")
check(daemon.player_skill([unknown])[unknown] == daemon.SKILL_NEW, "an unknown player = the new-player rating")
with daemon._dblock, daemon.dbc() as c:
    c.execute("DELETE FROM match_stats")
check(daemon.player_skill([T[0]])[T[0]] == sk[T[0]], "cached for SKILL_CACHE_S")

# 3. the split: the two strongest go to different teams and the rating sums end close
t0, t1 = daemon.split_teams(T, {}, sk, set(), [])
check(len(t0) == 4 and len(t1) == 4, "4 v 4")
check((T[0] in t0) != (T[1] in t0), "the two strongest on different teams (%s v %s)" % ([NAMES[T.index(x)] for x in t0], [NAMES[T.index(x)] for x in t1]))
d = abs(sum(sk[x] for x in t0) - sum(sk[x] for x in t1))
check(d < 0.05, "rating sums within 0.05 (%.3f)" % d)

# 4. a lone joiner of an even match takes the weaker team (rating sums) when that team has a slot
MM = daemon.MM
JOIN = T[7]
def run(mid, pl, departed=()):
    now = time.time()
    LOGS.clear()
    with MM.lock:
        for m in list(MM.matches):
            MM.matches.pop(m, None)
        MM.matches[mid] = list(pl); MM.formed[mid] = now - 200; MM.launched.add(mid); MM.started.add(mid); MM.started_t[mid] = now - 150
        MM.qtime[mid] = {}
        MM.departed[mid] = set(departed)
        daemon.MATCH_MAP[frozenset(pl)] = next(iter(daemon.MAPS)) if isinstance(daemon.MAPS, dict) else 0
        for t in departed: MM.departed_t[t] = now - 600
        MM.queue[JOIN] = now; MM.seen[JOIN] = now
    for t in pl:
        if t not in departed: MM.jip_clock(t, 400.0, 600.0, False)
    why = []
    r = MM.jip_join(JOIN, why)
    return r, why, [l for l in LOGS if "weaker team" in l]
daemon._skill_cache.clear()
for t in T: daemon._skill_cache[t] = (time.time(), sk[t])
# A: team 0 (even indexes) = Cat Dog Gnu (weak), team 1 = Ace Bee Eel: the next index 6 is team 0 = the weak team
r, why, wl = run("sbmmA001", [T[2], T[0], T[3], T[1], T[6], T[4]])
check(r is not None and r[1] % 2 == 0 and wl, "A: joiner -> weaker team 0 (%s, %s, %s)" % (r and r[1], wl[:1], why))
# B: team 0 strong: the weak team 1 has no slot (only index 6 is free): the joiner takes index 6 as before, no weaker-team log
MM.queue.pop(JOIN, None); MM._in_match = getattr(MM, "_in_match")
r, why, wl = run("sbmmB001", [T[0], T[2], T[1], T[3], T[4], T[6]])
check(r is not None and r[1] == 6 and not wl, "B: weak team without a slot: next index as before (%s, %s)" % (r and r[1], why))
# C: 4 v 4 with index 3 (team 1) and 4 (team 0) gone long ago = 3 v 3, team 1 weak: the joiner reuses index 3
G3, G4 = tok("Gone3"), tok("Gone4")
r, why, wl = run("sbmmC001", [T[0], T[2], T[1], G3, G4, T[3], T[4], T[6]], departed=(G3, G4))
check(r is not None and r[1] == 3 and wl, "C: joiner -> weaker team 1 in the free index 3 (%s, %s, %s)" % (r and r[1], wl[:1], why))
print("ALL OK" if not FAILS else "%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
