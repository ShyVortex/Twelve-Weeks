"""Live: party of 4 + two solos. A ready party that is short of players holds the solos back (no 1v1 without it), the wait says why.
Offline, plain python, temp DB, no sockets. Run: python tools/tests/test_party_queue.py"""
import os, sys, tempfile, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)
def tok(name): return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Jay", "Jask", "Truth", "Mother", "Notq", "Gmon", "Solo7", "Solo8"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_FILL_WAIT="0", T2R_QUEUE_SETTLE="0", T2R_P2P="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
for t in T: daemon.PRES.touch(t, "x")
MM = daemon.MM
LOGS = []
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
notes = []
daemon.SOCIAL.note = lambda t, kind, who="": notes.append((t, kind, who))

def reset():
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed", "departed_t"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.last_arrival = 0; MM._hold_since = 0.0
    daemon.PARTIES.of.clear(); daemon.PARTIES.inv.clear(); daemon.PARTIES.leaders.clear()
    LOGS.clear(); notes.clear()
    for a in ("_wait_logged", "_phold_logged", "_pneed_noted"):
        MM.__dict__.pop(a, None)
def qput(i, age):
    now = time.time(); MM.queue[T[i]] = now - age; MM.seen[T[i]] = now; MM.settle[T[i]] = 0
def mkparty(idx):
    for i in idx: daemon.PARTIES.of[T[i]] = "pp"
    daemon.PARTIES.leaders["pp"] = T[idx[0]]

# the exact live sequence: party of 4 all ready, then two solos
reset(); mkparty([0, 1, 2, 3])
for i in range(4): qput(i, 70)
mid, pl = MM.try_form()
check(mid is None, "party of 4 alone does not form")
check(any("party of 4" in l and "needs 7" in l for l in LOGS), "QUEUE-WAIT names the party size and players needed: " + str([l for l in LOGS if "QUEUE-WAIT" in l]))
check({n[0] for n in notes} == set(T[:4]) and all(n[1] == "pneed" and n[2] == "3" for n in notes), "every party member gets a pneed note (3 more)")
qput(4, 0); qput(5, 0)
mid, pl = MM.try_form()
check(mid is None, "two solos do NOT form a 1v1 and leave the ready party behind")
check(any("PARTY-HOLD" in l for l in LOGS), "PARTY-HOLD logged")
qput(6, 0)
mid, pl = MM.try_form()
check(mid is not None and len(pl) == 7 and all(T[i] in pl for i in range(4)), "party of 4 + 3 solos forms a 7-player match with the party whole")
t0, t1 = daemon.split_teams(pl, {t: daemon.PARTIES.pid(t) for t in pl if daemon.PARTIES.pid(t)})
check(({*t0} >= set(T[:4]) or {*t1} >= set(T[:4])), "party members on one team")

# solos leave: the party keeps waiting; after the hold expires the solos may play without it
reset(); mkparty([0, 1, 2, 3])
for i in range(4): qput(i, 200)
qput(4, 0); qput(5, 0)
mid, pl = MM.try_form()
check(mid is not None and set(pl) == {T[4], T[5]}, "hold expired (party waited 200 s): the solos play on")
reset(); mkparty([0, 1, 2, 3])
for i in range(4): qput(i, 10)
qput(4, 0); qput(5, 0)
check(MM.try_form()[0] is None, "fresh party holds the solos")
daemon.PARTY_HOLD_S = 0
mid, pl = MM.try_form()
check(mid is not None and set(pl) == {T[4], T[5]}, "T2R_PARTY_HOLD_S=0: old behaviour (1v1 of the solos)")
daemon.PARTY_HOLD_S = 120

# member leaving mid-queue: the party shrinks, the rest forms normally
reset(); mkparty([0, 1, 2, 3])
for i in range(4): qput(i, 5)
for i in (4, 5, 6): qput(i, 0)
del MM.queue[T[3]]; daemon.PARTIES.of.pop(T[3])            # one member cancels and leaves the party: 3 + 3 solos = 6 >= 5
mid, pl = MM.try_form()
check(mid is not None and len(pl) == 6, "party of 3 + 3 solos forms after a member left")

# a party bigger than the free slots waits (size 4: 3 + 1 solo)
import social
Q = social.Parties(max_size=4); Q.of.update({"a": "p", "b": "p", "c": "p"}); Q.leaders["p"] = "a"
sf = social.party_shortfall(["a", "b", "c", "x"], Q, 8, social.pick_units(["a", "b", "c", "x"], Q, 8))
check(sf and list(sf.values())[0][1] == 1, "party_shortfall: party of 3 + 1 solo is 1 short")
check(not social.party_shortfall(["a", "b", "c", "x", "y"], Q, 8, ["a", "b", "c", "x", "y"]), "no shortfall when the party is chosen")

# lobby list before matchmaking: party header + mates, solo = nothing
reset()
check(daemon.party_lobby_names(T[0]) == [], "solo player: no party rows")
mkparty([0, 1])
check(daemon.party_lobby_names(T[0]) == [b"PARTY 2/4", b"Jask (party)"], "leader sees PARTY 2/4 + mate: " + str(daemon.party_lobby_names(T[0])))
check(daemon.party_lobby_names(T[1]) == [b"PARTY 2/4", b"Jay (party lead)"], "member sees PARTY 2/4 + leader")
fr = daemon.lobby_list_frame(daemon.party_lobby_names(T[0]))
check(fr[2] == 0x17 and fr[3] == 2, "frame is op 0x17 with 2 rows")
daemon.PARTIES.of[T[2]] = "pp"
check(daemon.party_lobby_names(T[0])[0] == b"PARTY 3/4", "count follows a join")
daemon.PARTIES.of.pop(T[1]); daemon.PARTIES.of.pop(T[2])
check(daemon.party_lobby_names(T[0]) == [], "disband / leave: list empties")
mkparty([0, 1])
check(b"PARTY 2/4" in daemon.searching_frame(T[0]), "searching page starts with the party header")
print("done", len(FAILS), "failure(s)")
sys.exit(1 if FAILS else 0)
