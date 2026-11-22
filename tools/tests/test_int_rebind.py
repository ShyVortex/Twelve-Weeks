"""The Interrogation state follows the player's CURRENT match (crashed out of a running Interrogation match on Supermarket,
joined a Resort match: the server kept answering with Supermarket's map + lockbox spots). Run: python tests/test_int_rebind.py"""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)
def tok(n):
    return ("%02x" % n) * 32
T = [tok(i) for i in range(1, 9)]
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8",
                  T2R_P2P="0", T2R_DB=os.path.join(tmp, "t2r.db"))
import daemon, interrogation  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "t2r.db"); daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.evt = lambda *a, **k: None
MM, INT = daemon.MM, daemon.INT

def poll(t):
    pl = t.encode("latin1") + bytes([interrogation.SUB_POLL]) + (1).to_bytes(2, "little")
    fr = daemon.interrogation_op(pl)
    return fr[3:].decode() if fr else ""

def live(mid, players):
    now = time.time()
    with MM.lock:
        MM.matches[mid] = list(players); MM.formed[mid] = now; MM.launched.add(mid); MM.started.add(mid); MM.started_t[mid] = now; MM.qtime[mid] = {}

A = T[0]
# match 1: Interrogation on map 23
live("aaaa0001", T[:6])
INT.start("aaaa0001", T[:6], 23, mode="interrogation")
check("map=23" in poll(A) and "on=1" in poll(A), "in the Interrogation match: its state (map 23)")
# A crashes out of it (departed) and joins a running Supply Raid match on Resort (no INT record)
with MM.lock: MM.departed.setdefault("aaaa0001", set()).add(A)
live("bbbb0002", [A] + T[6:8])
r = poll(A)
check(r.startswith("on=0"), "joined a match without a record: on=0, not the old match's state (%r)" % r[:40])
check("map=23" not in r, "no stale map 23")
check(INT.by_token.get(A) is None, "the stale binding is gone")
# the old match still answers its own players
check("map=23" in poll(T[1]), "the old match's other players still get its state")
# A then plays an Interrogation match on map 4 (JIP into it: INT.roster adds A)
with MM.lock: MM.ended.add("bbbb0002")
live("cccc0003", [A] + T[2:5])
INT.start("cccc0003", [T[2], T[3], T[4]], 4, mode="interrogation")
r = poll(A)
check("map=4" in r and "on=1" in r, "current match has a record (A not in its start list yet): bound to it (%r)" % r[:40])
# a player in no match keeps its record (an ended match shows the win to late clients)
B = T[5]
with MM.lock: MM.departed.setdefault("aaaa0001", set()).add(B)
INT.by_token[B] = "aaaa0001"
check("map=23" in poll(B), "a token in no match keeps its last record")
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
