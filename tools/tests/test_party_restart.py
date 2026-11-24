"""Parties survive a daemon restart: the live state carries them and the start puts them back.
Run: python tests/test_party_restart.py   (offline, temp DB, no sockets)."""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Lead", "Mate1", "Mate2", "Mate3", "Solo", "Other"]
T = [tok(n) for n in NAMES]
LEAD, M1, M2, M3, SOLO, OTHER = T
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8",
                  T2R_MIN_PLAYERS="2", T2R_FILL_WAIT="0", T2R_P2P="0", T2R_LIVE_STATE="1", T2R_DB=os.path.join(tmp, "t2r.db"))
import daemon  # noqa: E402
import social  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "t2r.db")
daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
daemon.evt = lambda *a, **k: None
P = daemon.PARTIES

# a party of 4 led by LEAD (M1, M2 ready, M3 not), and a party of 2 that loses a member before the save
pid = "2bb3e1"
for t in (LEAD, M1, M2, M3):
    P.of[t] = pid
P.leaders[pid] = M2                                  # promoted: not the first member
P.ready |= {M1, M2}
P.of[SOLO] = "aaaaaa"; P.of[OTHER] = "aaaaaa"
P._leave(OTHER, "left")                              # (a party of one is no party: SOLO is out too)
check(P.pid(SOLO) is None, "a party left with one member is gone before the save")

check(not os.path.exists(daemon.live_path()), "(no live file yet)")
check(daemon.live_save(), "live state written with a party and no match running")

# what the restart does to memory
P.of.clear(); P.leaders.clear(); P.ready.clear(); P.grace.clear()
# OTHER made a new party with SOLO between the save and the load (cannot really happen, but a token in a party keeps it)
P.of[M3] = "bbbbbb"; P.of[SOLO] = "bbbbbb"

now = time.time()
daemon.live_load(now)
check(P.pid(LEAD) == pid and P.pid(M1) == pid and P.pid(M2) == pid, "the party is back with its id")
check(P.pid(M3) == "bbbbbb", "a member already in another party keeps that one")
check(P.leader(LEAD) == M2, "the promoted leader is the leader again")
check(M1 in P.ready and M2 in P.ready and LEAD not in P.ready, "ready flags restored")
check(len(P.members(LEAD)) == 3, "three members")

# the first gc pass after the start: nobody has reconnected yet (empty keep set)
dropped = P.gc({M3, SOLO}, now + 10)
check(P.pid(LEAD) == pid and len(P.members(LEAD)) == 3, "gc right after the start keeps the restored party (dropped %d)" % dropped)
# M1 reconnects, LEAD and M2 never do: after the grace they time out like before (leader gone = the next member leads)
P.gc({M1, M3, SOLO}, now + social.Parties.RESTORE_GRACE + 1)
check(P.pid(M1) is None, "after the grace the ones that never came back are dropped (the party of one with them)")
check(P.pid(M3) == "bbbbbb", "the other party is untouched")
check(not P.grace, "grace entries are cleaned up")

# restore() itself: junk is ignored, a saved party of one is not restored
P.of.clear(); P.leaders.clear(); P.ready.clear(); P.grace.clear()
n = P.restore({"of": [[LEAD, "cccccc"], ["x"], None, [M1, 5], [M2, "dddddd"]], "leaders": {"cccccc": M1}, "ready": [LEAD, 7]}, now)
check(n == 0 and not P.of, "broken entries and parties of one are not restored")
n = P.restore(None, now)
check(n == 0, "no saved parties (old file) is fine")
n = P.restore({"of": [[LEAD, "cccccc"], [M1, "cccccc"]], "leaders": {"cccccc": OTHER}}, now)
check(n == 2 and P.leader(M1) == LEAD, "a saved leader that is not a member falls back to the first member")

print("\n%d FAIL" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
