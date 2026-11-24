"""Stable search lobbies (a player seen in the lobby stays until they back out): lobbybook.py + the daemon wiring (MatchMaker._book_form,
searching_frame, the LOBBY chat key, jip_ready, cancel). Includes a replay of a recorded case and a fuzz of the pure book.
Run: python tools/tests/test_lobby_book.py   (temp DB, no sockets)."""
import os, random, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

# ================================================================ the pure book
import lobbybook  # noqa: E402
clk = [1000.0]
B = lobbybook.LobbyBook(8, now=lambda: clk[0])
yes = lambda m, n: True
cap8 = lambda lb, inc=(): 8
lid_a, why = B.place("a", ["a"], yes, cap8)
lid_b, _ = B.place("b", ["b"], yes, cap8)
check(lid_a == lid_b and why == "new", "the second searcher joins the first one's lobby")
no_c = lambda m, n: "c" not in n and "c" not in m
lid_c, _ = B.place("c", ["c"], no_c, cap8)
check(lid_c != lid_a, "a searcher that does not fit (mode / ping) gets its own lobby")
for i in range(7):
    B.place("p%d" % i, ["p%d" % i], yes, cap8)
check(len(B.members(lid_a)) == 8 and B.lobby_of("p5") == lid_a and B.lobby_of("p6") != lid_a, "a lobby never takes more than 8; the 9th opens a new one")
B.away("a")
clk[0] += 5
check(B.place("a", ["a"], yes, cap8) == (lid_a, "back") and not B.get(lid_a).away, "back within the grace: the same seat (a page reset / reconnect)")
B.away("b")
clk[0] += lobbybook.GRACE_S + 1
gone = B.expire()
check(gone == [("b", lid_a)] and B.lobby_of("b") is None, "not back within the grace: out of the lobby")
lid_b2, why = B.place("b", ["b"], yes, cap8)
check(lid_b2 == lid_a and why == "rejoin", "searching again soon after: back into its old lobby when there is room")
# countdown backout: the lobby stays open without the leaver, who is kept out of it for BACKOUT_BLOCK_S
B.launched(lid_a, "m1")
check(B.get(lid_a).mid == "m1" and B.key_for_mid("m1") == lid_a, "launched: the match id maps to the lobby (chat room)")
B.cancelled("m1", "b")
check(B.get(lid_a).mid is None and B.lobby_of("b") is None and "b" not in B.members(lid_a) and len(B.members(lid_a)) == 7,
      "cancelled by b: the other 7 keep their lobby, b is out")
lid_b3, _ = B.place("b", ["b"], yes, cap8)
check(lid_b3 != lid_a, "b is not put back into the lobby it cancelled (blocked %.0f s)" % lobbybook.BACKOUT_BLOCK_S)
# merge: two small lobbies that fit become one, the bigger keeps its id; a post-match lobby keeps its id even when smaller
B2 = lobbybook.LobbyBook(8, now=lambda: clk[0])
l1, _ = B2.place("x1", ["x1"], lambda m, n: False, cap8)
l2, _ = B2.place("y1", ["y1"], lambda m, n: False, cap8)
B2.place("y2", ["y2"], lambda m, n: "y1" in m, cap8)
check(l1 != l2 and len(B2.members(l2)) == 2, "two lobbies (no fit at placement)")
done = B2.merge_pass(yes, cap8)
check(done == [(l2, l1)] and sorted(B2.members(l2)) == ["x1", "y1", "y2"] and B2.get(l1) is None, "merge: the smaller lobby moves into the bigger one")
B3 = lobbybook.LobbyBook(8, now=lambda: clk[0])
lp, why = B3.place("r1", ["r1"], yes, cap8, src="old")
check(lp == "mold" and why.startswith("post-match lobby"), "the first returner opens the post-match lobby (id of the old match's lobby)")
for t in ("s1", "s2", "s3"):
    B3.lobbies.setdefault("Lsolo", None)
    B3.lobbies.pop("Lsolo")
lb_s = B3._new(clk[0]); [B3._add(lb_s, t, clk[0]) for t in ("s1", "s2", "s3")]
B3.merge_pass(yes, cap8)
check(sorted(B3.members("mold")) == ["r1", "s1", "s2", "s3"], "merge: the post-match lobby keeps its id (its chat room, its returners)")
# parties: a member joins its mate's lobby; no room -> the party moves together
B4 = lobbybook.LobbyBook(4, now=lambda: clk[0])
cap4 = lambda lb, inc=(): 4
B4.place("q1", ["q1", "q2"], yes, cap4)
for t in ("o1", "o2", "o3"):
    B4.place(t, [t], yes, cap4)
lq, why = B4.place("q2", ["q2", "q1"], yes, cap4)
check(why == "party-moved" and B4.lobby_of("q1") == lq and sorted(B4.members(lq)) == ["q1", "q2"], "a party mate with no room left: the party moves to a new lobby together")
check(B.check() and B2.check() and B3.check() and B4.check(), "book invariants hold")

# ---- fuzz: random arrivals / page resets / backouts / merges / launches; nobody leaves a lobby except by an allowed reason
rng = random.Random(1124)
for seed in range(40):
    clk[0] = 5000.0
    F = lobbybook.LobbyBook(8, now=lambda: clk[0])
    removed = []
    F.log = lambda s, removed=removed: removed.append(s)
    pool = ["t%d" % i for i in range(30)]
    modes = {t: rng.choice((0, 0, 1)) for t in pool}
    fit = lambda m, n: len({modes[x] for x in list(m) + list(n)}) == 1
    seen = {}                           # token -> its lobby members last pass (who it "sees")
    for step in range(300):
        clk[0] += rng.uniform(0.2, 3.0)
        t = rng.choice(pool)
        op = rng.random()
        if op < 0.45:
            F.place(t, [t], fit, cap8)
        elif op < 0.6:
            F.away(t)
        elif op < 0.65 and F.lobby_of(t):
            F.remove(t, "backed out (fuzz)")
        elif op < 0.75:
            F.merge_pass(fit, cap8)
        elif op < 0.8:
            lbs = [lb for lb in F.open_lobbies() if lb.members]
            if lbs:
                F.launched(rng.choice(lbs).lid, "m%d_%d" % (seed, step))
        elif op < 0.85:
            ms = [lb for lb in F.lobbies.values() if lb.mid and lb.members]
            if ms:
                lb = rng.choice(ms)
                F.cancelled(lb.mid, rng.choice(lb.members))
        F.expire()
        F.check()
        # who disappeared from someone's lobby without an allowed reason?
        for u, prev in list(seen.items()):
            now_m = set(F.mates(u)) if F.lobby_of(u) else None
            if now_m is None:
                continue
            for v in prev - now_m:
                if F.lobby_of(v) is not None and F.lobby_of(v) != F.lobby_of(u):
                    raise AssertionError("seed %d step %d: %s moved from %s's lobby to another lobby without leaving" % (seed, step, v, u))
        seen = {u: set(F.mates(u)) for u in pool if F.lobby_of(u)}
check(True, "fuzz: 40 runs x 300 ops - invariants hold, nobody is moved from one lobby to another (only a leave or a party move takes a member out)")

# ================================================================ the daemon
def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Ava", "Ben", "Cal", "Dan", "Eve", "Fay", "Gus", "Hal", "Ivy", "Jon", "Kim", "Lou", "Max", "Ned", "Oli", "Pat"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8",
                  T2R_MIN_PLAYERS="2", T2R_FILL_RULE="classic", T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0",
                  T2R_LOBBY_BOOK="1", T2R_DB=os.path.join(tempfile.mkdtemp(), "t2r.db"))
os.chdir(tempfile.mkdtemp())
import daemon  # noqa: E402
daemon.DB_PATH = os.environ["T2R_DB"]
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.evt = lambda *a, **k: None
LOGS = []
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
daemon.player_skill = lambda toks: {t: 0.6 for t in toks}
MM = daemon.MM
check(daemon.book_on(), "stable lobbies on by default (T2R_LOBBY_BOOK=1 + T2R_LOBBY_KEEP=1)")

def reset():
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "left", "ended_at", "started_t"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.last_arrival = 0.0; MM._hold_since = 0.0
    MM.rq.t.clear(); MM.rq.first.clear(); MM.rq.next.clear(); daemon.RQ_CAP.clear()
    MM.book.__init__(daemon.MATCH_SIZE, log=daemon.log)
    daemon.PARTIES.of.clear(); daemon.PARTIES.leaders.clear()
    daemon.PING.clear(); daemon.PING_AT.clear()
    for t in T: daemon.PRES.touch(t, "x")

def search(t, ago=100.0):
    now = time.time()
    MM.queue[t] = now - ago; MM.seen[t] = now; MM.settle[t] = 0
    if t in MM.rq.t: MM.rq.searching(t)              # (as MM.enqueue: a ticket holder searches again)

def finished(players, age=11.0):
    mid = "f%08x" % (abs(hash(tuple(players))) % 0xffffffff)
    now = time.time()
    MM.matches[mid] = list(players); MM.launched.add(mid); MM.started.add(mid); MM.formed[mid] = now - 600
    for t in players: daemon.RQ_CAP[t] = now
    MM.end(mid)
    MM.ended_at[mid] = now - age
    with MM.rq.lock:
        for t in players:
            if t in MM.rq.t: MM.rq.t[t][1] = now - age
    return mid

def page(t):
    """The names on t's searching page."""
    f = daemon.searching_frame(t)
    return {n for n in NAMES if n.encode() in f and n != NAMES[T.index(t)]}

# ---- 10 searchers: a lobby of 8 + a lobby of 2. The 8 form; the 2 stay together and see only each other
reset()
for t in T[:10]: search(t)
r = MM.try_form()
rest = [t for t in T[:10] if t not in (r[1] or [])]
check(r[0] is not None and len(r[1]) == 8 and len(rest) == 2 and MM.book.lobby_of(rest[0]) == MM.book.lobby_of(rest[1]),
      "10 searchers: 8 form a match, the other 2 share their own lobby")
check(page(rest[0]) == {NAMES[T.index(rest[1])]}, "the searching page lists only the own lobby (%s)" % page(rest[0]))
k0, k1 = daemon._lobby_chat_key(rest[0]), daemon._lobby_chat_key(rest[1])
k8 = daemon._lobby_chat_key(r[1][0])
check(k0 and k0 == k1 and k8 and k8 != k0, "LOBBY chat: one room per lobby (%s / %s / %s)" % (k0, k1, k8))

# ---- countdown backout: the others keep their lobby and start again together (no reshuffle with the queue)
reset()
for t in T[:5]: search(t)
r = MM.try_form()
lid = MM.book.lobby_of(T[0])
check(r[0] is not None and len(r[1]) == 5, "5 searchers form a match")
others = MM.cancel(T[2])
check(sorted(others) == sorted([T[0], T[1], T[3], T[4]]) and MM.book.lobby_of(T[0]) == lid and MM.book.lobby_of(T[2]) is None,
      "Cal backs out of the countdown: the other 4 stay in their lobby, Cal is out of it")
search(T[11])                                       # a newcomer arrives in the relaunch wait
for t in others: MM.seen[t] = time.time()
MM.try_form()
check(MM.book.lobby_of(T[11]) == lid, "a newcomer during the relaunch wait joins that lobby (it sees them, they see it)")
MM.book.get(lid).wait_until = 0
MM.dequeue(T[0])                                     # Ava's 0x02 right after the cancel (page reset)
r2 = MM.try_form()
check(r2[0] is None and MM.book.lobby_of(T[0]) == lid, "Ava's page reset (0x02): the seat waits, the lobby does not start without her")
search(T[0])
r2 = MM.try_form()
check(r2[0] is not None and sorted(r2[1]) == sorted(others + [T[11]]), "Ava searches again: the same lobby starts, with Ava (%s)" % (r2[1] and [NAMES[T.index(t)] for t in r2[1]]))
search(T[2])
MM.try_form()
check(MM.book.lobby_of(T[2]) != MM.book.lobby_of(T[0]), "Cal searching again goes elsewhere")

# ---- replay of a recorded case: Ava's lobby (5 back, Fay on the screens) + the party Ivy / Jon / Kim searching at the same time.
# Before: the page listed all of them, the party went into another match and the lobby started with 5. Now the party is in a lobby of its own
# or in Ava's, and whatever the page shows is what starts.
reset()
lob = [T[0], T[1], T[2], T[3], T[4], T[5]]          # Ava Ben Cal Dan Eve Fay
mid = finished(lob)
for t in lob[:5]: search(t, ago=5)
pp = "party1"
for t in T[8:11]: daemon.PARTIES.of[t] = pp
daemon.PARTIES.leaders[pp] = T[8]
for t in T[8:11]: search(t, ago=30)
r = MM.try_form()
lk = MM.book.lobby_of(T[0])
lp = MM.book.lobby_of(T[8])
check(r[0] is None, "Fay still on the post-match screens: nothing forms yet (%s)" % (r[1] and [NAMES[T.index(t)] for t in r[1]]))
check(all(MM.book.lobby_of(t) == lk for t in lob[:5]), "Ava's 5 share the post-match lobby")
check(len({MM.book.lobby_of(t) for t in T[8:11]}) == 1, "the party is in one lobby")
pk = page(T[0])
check(("Ivy" in pk) == (lp == lk), "Ava's page shows the party only if they share her lobby (%s)" % sorted(pk))
check("Fay" in pk, "Fay is listed (IN SUMMARY) on Ava's page")
# the wait ends (Fay slow): whatever forms is a whole lobby, and the party never ends up in another match while listed with Ava
MM.rq.release_s = 0.0
with MM.rq.lock:
    for t in MM.rq.t: MM.rq.t[t][1] = time.time() - 200
r = MM.try_form()
if lp == lk:
    check(r[0] is not None and set(T[8:11]) <= set(r[1]) and set(lob[:5]) <= set(r[1]), "shared lobby: the party plays with Ava's lobby")
else:
    check(r[0] is None or set(r[1]) in (set(lob[:5]), set(T[8:11])) or set(r[1]) >= set(lob[:5]) | set(T[8:11]),
          "separate lobbies: a match is one whole lobby (%s)" % (r[1] and [NAMES[T.index(t)] for t in r[1]]))
MM.rq.release_s = daemon.LOBBY_RELEASE_S

# ---- a lobby of more than one unit is never pulled apart by a join in progress
reset()
search(T[0]); search(T[1])
MM.try_form()
check(MM.book.lobby_of(T[0]) == MM.book.lobby_of(T[1]), "two searchers share a lobby")
rd = MM.jip_ready()
check(T[0] not in rd and T[1] not in rd, "jip_ready leaves a 2-player lobby out (it is not split by a join)")

print("ALL OK" if not FAILS else "%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
