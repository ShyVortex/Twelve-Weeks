"""Queue stays after a match: the players still in a finished match search again by themselves after their post-match screens and their
next lobby waits until all of them search (tools/requeue.py + daemon MatchMaker.end / try_form / jip_ready, 0xBD 'rq=' / 'rqw=' for the client text).
Run: python tools/tests/test_requeue.py   (no sockets are opened, temp DB)."""
import os, sys, tempfile, time, struct
os.environ.setdefault("T2R_LOBBY_BOOK", "0")   # these cases test the queue without the stable search lobbies (tools/lobbybook.py)
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

# ---------------------------------------------------------------- the pure bookkeeping (tools/requeue.py)
import requeue  # noqa: E402
clk = [1000.0]
rq = requeue.Requeue(wait_max=120.0, ticket_s=300.0, offline_s=30.0, now=lambda: clk[0])
sil = {}
silence = lambda t: sil.get(t, 0.0)
inm = set()
in_match = lambda t: t in inm
check(rq.open("m1", ["a", "b", "c", "a", ""]) == ["a", "b", "c"], "tickets for every listed player once")
held, wait, gone = rq.held([], silence, in_match)
check(not held and wait == {} and not gone, "nobody searching: nothing held")
check(rq.searching("a") == "m1" and rq.searching("zz") is None, "a ticket holder's search is noted (others: None)")
held, wait, _ = rq.held(["a", "x"], silence, in_match)
check(held == {"a"} and sorted(wait["m1"]) == ["b", "c"], "a waits for b and c, a stranger is never held (%s %s)" % (held, wait))
check(rq.status("a", ["a"], silence, in_match) == (True, 2), "status: ticket, waiting for 2")
check(rq.status("b", ["a"], silence, in_match) == (True, 0), "status of a player still on the screens: ticket, not held")
check(rq.status("x", ["a"], silence, in_match) == (False, 0), "status without a ticket")
rq.searching("b")
sil["c"] = 31.0
held, wait, gone = rq.held(["a", "b"], silence, in_match)
check(not held and ("c", "offline (silent 31 s)") in gone, "c silent 31 s: dropped, a and b released (%s)" % gone)
# cancel / new match
clk[0] = 2000.0; sil.clear()
rq.open("m2", ["p", "q", "r"])
rq.searching("p")
check(rq.held(["p"], silence, in_match)[0] == {"p"}, "p held for q, r")
check(rq.drop("q") and not rq.drop("q"), "q cancels its search: ticket gone (once)")
inm.add("r")
held, wait, gone = rq.held(["p"], silence, in_match)
check(not held and ("r", "in a match again") in gone, "r in another match: dropped, p released")
inm.clear()
# the wait cap
clk[0] = 3000.0
rq.open("m3", ["s", "t"])
rq.searching("s")
clk[0] = 3119.0
check(rq.held(["s"], silence, in_match)[0] == {"s"}, "119 s after the end: still held")
clk[0] = 3120.0
check(not rq.held(["s"], silence, in_match)[0], "120 s after the end: released (the slow one is not waited for)")
check(rq.has("t"), "the slow one keeps its ticket (searches by itself when it reaches the menu)")
clk[0] = 3300.0
held, wait, gone = rq.held(["s"], silence, in_match)
check(not rq.has("t") and any(t == "t" and "expired" in w for t, w in gone), "300 s after the end: ticket expired")

# ---------------------------------------------------------------- the daemon
def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina", "Hal"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2", T2R_FILL_RULE="classic",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0", T2R_SECOND_MATCH_MIN="6")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
LOGS = []
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
MM = daemon.MM
check(daemon.REQUEUE and daemon.REQUEUE_WAIT_MAX == 90.0 and daemon.REQUEUE_TICKET_S == 300.0, "defaults: on, wait 90 s, ticket 300 s")
check(daemon.LOBBY_KEEP and daemon.LOBBY_RELEASE_S == 30.0 and daemon.LOBBY_MIN_GAP_S == 10.0, "lobby defaults: on, release 30 s, min gap 10 s")

def reset():
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "left", "ended_at", "started_t"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.last_arrival = 0.0; MM._hold_since = 0.0
    MM.rq.t.clear(); MM.rq.first.clear(); MM.rq.next.clear(); daemon.RQ_CAP.clear()
    MM._rq_logged = 0.0; MM._lobby_fill_logged = 0.0
    daemon.PARTIES.of.clear(); daemon.PARTIES.leaders.clear()
    for t in T: daemon.PRES.touch(t, "x")
    LOGS.clear(); FORMED.clear(); daemon.MODEQ.pref.clear()

MIDS = [0]
def finished(players, mid=None, capable=None, departed=(), age=11.0):
    """A match that ran and just got its result (MatchMaker.end); `capable` = tokens whose ext reported flag 0x20."""
    if mid is None: MIDS[0] += 1; mid = "e%d" % MIDS[0]          # (a fresh id per scenario: the mode table remembers match ids)
    MM.matches[mid] = list(players); MM.launched.add(mid); MM.started.add(mid); MM.formed[mid] = time.time() - 600
    for t in departed: MM.departed.setdefault(mid, set()).add(t)
    for t in (players if capable is None else capable): daemon.RQ_CAP[t] = time.time()
    MM.end(mid)
    if age:
        ago(age)
    return mid

def ago(sec, mid=None):
    """Move the finished match(es) `sec` s into the past (ticket end times and the first-search times)."""
    for e in MM.rq.t.values():
        if mid is None or e[0] == mid: e[1] -= sec
    for m in list(MM.rq.first):
        if mid is None or m == mid: MM.rq.first[m] -= sec

FORMED = []
def search(t):
    """The client's FIND MATCH (its own search page push): MatchMaker.enqueue (which may form the match at once), then it polls fresh."""
    r = MM.enqueue(t)
    MM.seen[t] = time.time()
    if r[0]: FORMED.append(r)
    return r
def formed():
    """The match the last searches / a matchmaker pass formed (None, None when none)."""
    r = MM.try_form()
    if r[0]: FORMED.append(r)
    return FORMED.pop() if FORMED else (None, None)

def bd(t):
    """The 0xBD reply text of the 0xBC poll."""
    rep = daemon.modeq_op(t.encode() + bytes([0, 0]))
    return rep[3:].decode()

# ---- 4 players finish a match: the first two back search, the lobby waits for the other two
reset()
mid = finished(T[:4])
check(sorted(MM.rq.t) == sorted(T[:4]), "every player of the finished match got a ticket")
check(" rq=1 rqw=0" in bd(T[0]), "on the scoreboard: ticket, not waiting (%r)" % bd(T[0]))
r1 = search(T[0]); r2 = search(T[1])
check(formed() == (None, None), "Alice + Bob search: NO match from the two (Carol, Dave still on the post-match screens)")
check(" rq=1 rqw=2" in bd(T[0]), "Alice's poll: waiting for 2 players -> WAITING FOR PLAYERS... (%r)" % bd(T[0]))
check(any("requeue: HOLD" in l for l in LOGS), "HOLD logged")
check(MM.jip_ready() == [], "a held searcher is not offered to a running match either")
search(T[2])
check(formed() == (None, None) and " rqw=1" in bd(T[0]), "Carol searches too: still waiting for Dave")
search(T[3])
m, pl = formed()
check(m is not None and sorted(pl) == sorted(T[:4]), "Dave searches: the lobby forms with all four (%s)" % (pl and [daemon.tag(t) for t in pl]))
check(not any(t in MM.rq.t for t in T[:4]), "tickets used up by the new match")
check(" rq=" not in bd(T[0]), "no ticket any more: no rq key (%r)" % bd(T[0]))

# ---- a stranger searching at the same time is not held
reset()
finished(T[:4])
search(T[0]); search(T[5])
m, pl = formed()
check(m is None or T[0] not in pl, "a held player is never in the stranger's match")
check(T[0] in MM.queue, "Alice stays queued (held)")

# ---- leavers, old exts, party members without their leader get no ticket
reset()
daemon.PARTIES.of[T[2]] = "pp"; daemon.PARTIES.of[T[6]] = "pp"; daemon.PARTIES.leaders["pp"] = T[6]
finished([T[0], T[1], T[2], T[3]], capable=[T[0], T[1], T[2]], departed=[T[1]])
check(sorted(MM.rq.t) == [T[0]], "ticket only for Alice (Bob left early, Carol's leader was not in the match, Dave's ext is old) %s" % [daemon.tag(t) for t in MM.rq.t])
search(T[0]); search(T[3])
m, pl = formed()
check(m is not None and sorted(pl) == sorted([T[0], T[3]]), "nobody left to wait for: Alice + Dave form at once")

# ---- party with its leader: both get tickets
reset()
daemon.PARTIES.of[T[0]] = "pp"; daemon.PARTIES.of[T[1]] = "pp"; daemon.PARTIES.leaders["pp"] = T[0]
finished(T[:4])
check(T[1] in MM.rq.t and T[0] in MM.rq.t, "a party member whose leader played gets a ticket too")

# ---- cancel the search: ticket gone, the others still wait only for the ones on the screens
reset()
finished(T[:4])
search(T[0]); search(T[1]); search(T[2])
check(formed() == (None, None), "Dave still on the screens: Alice, Bob, Carol held")
MM.dequeue(T[3])                          # Dave's session close right after MATCH-END: also 0x02, he is still on the screens
check(T[3] in MM.rq.t, "the 0x02 session close after the match end keeps a 'post' ticket")
MM.dequeue(T[2])                          # Carol backs out of the search page (0x02)
check(T[2] not in MM.rq.t and T[2] not in MM.queue, "a cancelled search drops the ticket")
check(formed() == (None, None) and " rqw=1" in bd(T[0]), "Alice + Bob still wait for Dave")
with daemon.PRES.lock:
    daemon.PRES.players[T[3]]["last"] = time.time() - 31
m, pl = formed()
check(m is not None and sorted(pl) == sorted(T[:2]), "Dave quit the game after the match (silent 31 s): Alice + Bob form without him and without Carol")
search(T[2])
check(T[2] in MM.queue and T[2] not in MM.rq.t, "Carol searching again later is a normal searcher")

# ---- Carol quits the game after the match (silent): not waited for
reset()
finished(T[:3])
search(T[0]); search(T[1])
with daemon.PRES.lock:
    daemon.PRES.players[T[2]]["last"] = time.time() - 31
m, pl = formed()
check(m is not None and sorted(pl) == sorted(T[:2]), "a player silent 31 s after the match is not waited for")
check(any("ticket ended: offline" in l for l in LOGS), "logged why")

# ---- the wait cap: 90 s after the end the searchers go on without the slow one
reset()
finished(T[:3])
search(T[0]); search(T[1])
check(formed() == (None, None), "held before the cap")
for e in MM.rq.t.values(): e[1] -= 80
m, pl = formed()
check(m is not None and sorted(pl) == sorted(T[:2]), "91 s after the end: the lobby forms without Carol")
check(T[2] in MM.rq.t and " rq=1 rqw=0" in bd(T[2]), "Carol keeps her ticket: her ext still searches by itself, not held")

# ---- the mode: the player's pick is kept (refreshed); with none on record the finished match's mode
reset()
daemon.MODEQ.pref.clear()
mid = finished(T[:2])
daemon.MODEQ.formed(mid, "interrogation")
daemon.MODEQ.set(T[0], 0)
with daemon.MODEQ.lock:
    daemon.MODEQ.pref[T[0]] = (0, daemon.MODEQ.now() - 3000)       # an old pick, still valid
search(T[0]); search(T[1])
check(daemon.MODEQ.get(T[0]) == 0 and daemon.MODEQ.now() - daemon.MODEQ.pref[T[0]][1] < 5, "Alice's own pick (Supply Raid) kept and refreshed")
check(daemon.MODEQ.get(T[1]) == daemon.modeq.MODES.index("interrogation"), "Bob had no pick: the match's mode (Interrogation)")
daemon.MODEQ.pref.clear()

# ---- a refused / kicked player ends its ticket
reset()
finished(T[:3])
search(T[0])
pid = __import__("hashlib").sha256(T[1].encode()).hexdigest()[:12]
r = daemon.admin_kick(pid, "test")
check(r.get("ok") and T[1] not in MM.rq.t, "admin kick drops the ticket (%s)" % r)

# ---- MatchMaker.end twice (client reports close, then the host's 0x12) opens the tickets once
reset()
mid = finished(T[:2])
MM.rq.searching(T[0])
MM.end(mid)
check(MM.rq.t[T[0]][2] == "search", "a second MM.end does not reset the tickets")

# ================================================================ PERSISTENT LOBBY (LOBBY_KEEP)
# ---- the release timer: 30 s after the first member is back, the lobby goes without the ones still on the screens; a stranger backfills
reset()
mid = finished(T[:4])
search(T[0]); search(T[1])
search(T[5])                              # Frank, a stranger, searches meanwhile
check(formed() == (None, None), "Alice + Bob back, Carol + Dave on the screens, Frank searching: nothing forms yet")
check(T[5] in MM.queue and any("LOBBY: hold" in l for l in LOGS), "Frank waits to fill the lobby's open seats (logged)")
b = bd(T[0])
rqs = int(b.split("rqs=")[1].split()[0]) if "rqs=" in b else -1
check(" rqw=2" in b and 25 <= rqs <= 30 and " rqb=2" in b and " rqp=2" in b, "0xBD: waiting for 2, next match in ~30 s, 2 back, 2 on the screens (%r)" % b)
ago(29, mid)
check(formed() == (None, None), "29 s after the first search: still waiting")
ago(2, mid)
m, pl = formed()
check(m is not None and sorted(pl) == sorted([T[0], T[1], T[5]]), "31 s after the first search: Alice + Bob + Frank form (%s)" % (pl and [daemon.tag(t) for t in pl]))
check(any("LOBBY: next match" in l for l in LOGS), "the lobby's next match is logged")
check(MM.rq.next_of(T[2]) == m and MM.rq.next_of(T[3]) == m, "Carol + Dave belong to the new match (they join it in progress)")
check(sorted(MM.rq.kept(m)) == sorted(T[2:4]), "two seats kept in the new match for Carol + Dave")
# Carol back while the new match is in its countdown: she never forms another match with a stranger, she waits to join hers
search(T[2]); search(T[6])
m2, pl2 = formed()
check(m2 is None or T[2] not in pl2, "Carol back during the new match's countdown: not put into another match")
check(T[2] in MM.queue, "Carol stays searching (joins her lobby's match once GAME-START went out)")
MM.started.add(m)
m3, pl3 = formed()
check(m3 is None or T[2] in pl3 or T[2] in MM.queue, "after GAME-START she is a normal searcher again if the join fails")

# ---- everybody back at once: the lobby waits for the minimum gap after the end (the old match's records are freed at 9 s)
reset()
mid = finished(T[:2], age=0)
search(T[0]); search(T[1])
check(formed() == (None, None), "both back 0 s after the end: held for the minimum gap")
ago(11, mid)
m, pl = formed()
check(m is not None and sorted(pl) == sorted(T[:2]), "11 s after the end: the same lobby forms its next match")

# ---- the lobby is formed first and together: a second released lobby or old searchers never split it
reset()
mid = finished(T[:3])
search(T[3]); MM.queue[T[3]] = time.time() - 300     # Dave queued long ago (first in queue order)
search(T[0]); search(T[1]); search(T[2])
m, pl = formed()
check(m is not None and all(t in pl for t in T[:3]), "all three lobby members are in the next match (%s)" % (pl and [daemon.tag(t) for t in pl]))

# ---- a waiting lobby with no room: strangers are not held
reset()
daemon.MATCH_SIZE, _ms = 4, daemon.MATCH_SIZE
mid = finished(T[:4])
search(T[0])
search(T[5]); search(T[6])
m, pl = formed()
check(m is not None and sorted(pl) == sorted(T[5:7]), "the lobby is full (4 of 4): Frank + Gina form their own match")
daemon.MATCH_SIZE = _ms

# ---- T2R_LOBBY_KEEP=0: the old requeue
reset()
daemon.LOBBY_KEEP = False
MM.rq.release_s = 0.0; MM.rq.min_gap = 0.0
finished(T[:4], age=0)
search(T[0]); search(T[1]); search(T[5]); search(T[6])
m, pl = formed()
check(m is not None and sorted(pl) == sorted(T[5:7]), "lobby off: strangers are not held for the lobby (old behaviour)")
daemon.LOBBY_KEEP = True
MM.rq.release_s = daemon.LOBBY_RELEASE_S; MM.rq.min_gap = daemon.LOBBY_MIN_GAP_S

# ---- the searching page's lobby rows: READY for a member back, an IN SUMMARY row for one still on the post-match screens
reset()
finished(T[:2])
search(T[0])
f = daemon.searching_frame(T[0])
check(b" (summary)" in f and daemon.get_name(T[1]).encode()[:24] + b" (summary)" in f, "Alice's lobby list has Bob's IN SUMMARY row")
search(T[1])
f = daemon.searching_frame(T[0])
check(b" (summary)" not in f, "Bob back: no IN SUMMARY row any more")

# ---- LOBBY chat: the players of the last match share a channel; a stranger has none
reset()
finished(T[:2])
S = daemon.SOCIAL
r = S._lobby_chat(T[0], "acc-a", daemon.social.S_LSAY, "gg, again?")
check(r.get("ok") == 1 and r["pchat"]["lines"] and r["pchat"]["lines"][-1]["t"] == "gg, again?" and r["lk"], "Alice's LOBBY line is stored (%s)" % r)
r2 = S._lobby_chat(T[1], "acc-b", daemon.social.S_LCHAT, "0")
check(r2.get("ok") == 1 and any(x["t"] == "gg, again?" and not x["me"] for x in r2["pchat"]["lines"]) and r2["lk"] == r["lk"], "Bob's poll reads it, same lobby key")
r3 = S._lobby_chat(T[5], "acc-x", daemon.social.S_LSAY, "hello?")
check(r3.get("ok") == 0 and r3.get("err") == "nolobby", "a stranger has no LOBBY channel (%s)" % r3)

# ---- T2R_REQUEUE=0: nothing changes
reset()
daemon.REQUEUE = False
finished(T[:3])
check(not MM.rq.t, "off: no tickets")
search(T[0]); search(T[1])
m, pl = formed()
check(m is not None, "off: the two form at once as before (%s)" % LOGS[-6:])
daemon.REQUEUE = True

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
