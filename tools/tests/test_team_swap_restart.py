"""In-match team swaps survive a daemon restart (auto balance moved a player, the deploy restart 66 s later put it back on its
slot-parity team in every roster reply, while its own ext kept the new team: one-sided friendly fire and wrong nametags).
Run: python tests/test_team_swap_restart.py   (offline, temp DB, no sockets)."""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina"]
T = [tok(n) for n in NAMES]
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8",
                  T2R_MIN_PLAYERS="2", T2R_FILL_WAIT="0", T2R_P2P="0", T2R_HOST_MIGRATION="1", T2R_LIVE_STATE="1", T2R_DB=os.path.join(tmp, "t2r.db"))
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "t2r.db")
daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
daemon.evt = lambda *a, **k: None
MM, HM = daemon.MM, daemon.HM

def roster_teams(t):
    """{slot: team} of the 0xE5 roster reply that token t gets, plus the 0xA7 swap block."""
    body = daemon.jip_poll(t.encode("latin1") + bytes([0x10]) + b"\0" * 8) if hasattr(daemon, "jip_poll") else None
    return body

MID = "0693abcd"
now = time.time()
with MM.lock:
    MM.matches[MID] = list(T); MM.formed[MID] = now - 120; MM.launched.add(MID); MM.started.add(MID); MM.started_t[MID] = now - 100; MM.qtime[MID] = {}
daemon.MATCH_MAP[frozenset(T)] = 4
HM.start(MID, T)
for t in T:
    daemon.LOADED.add(t); daemon.PRES.touch(t, "x")

check(daemon.team_in(MID, 6, T[6]) == 0, "slot 6 starts on its parity team 0")
daemon.team_swap_now(MID, 6, T[6], 1, "auto-balance")
check(daemon.team_in(MID, 6, T[6]) == 1, "auto balance moved slot 6 to team 1")

check(daemon.live_save(), "live state written")
# what the restart does to memory
for a in ("matches", "formed", "qtime", "departed", "clock", "joining", "lives", "started_t"):
    getattr(MM, a).clear()
MM.launched.clear(); MM.started.clear(); MM.ended.clear()
HM.matches.clear(); HM.by_token.clear(); daemon.TEAM_SWAP.clear(); daemon.READOPT.clear(); daemon.LOADED.clear()
check(daemon.team_in(MID, 6, T[6]) == 0, "(before the fix's restore: parity again)")

daemon.live_load()
check(MID in daemon.READOPT, "record waits for a claim")
daemon.readopt_claim(T[4])                      # Steven's re-attach / first poll
check(MID in MM.matches, "match re-adopted")
check(daemon.team_in(MID, 6, T[6]) == 1, "slot 6 is still on team 1 after the restart (got %d)" % daemon.team_in(MID, 6, T[6]))
check(daemon.roster_team_in(MID, 6, T[6]) == 1, "roster reply team for slot 6 = 1")
check(all(daemon.team_in(MID, i, T[i]) == daemon.team_of(i) for i in range(6)), "the other slots keep their parity teams")

# a record from an older daemon (no team_swap key) still loads
rec = {"mid": "old00001", "players": T[:2], "formed": now, "started_t": now, "launched": True, "departed": [], "joining": {}, "joining_loaded": [],
       "dep_vol": [], "dep_t": {}, "clock": None, "lives": None, "late_bonus": {}, "late_mult": {}, "saved": now}
daemon._readopt_apply("old00001", rec, T[0], now)
check("old00001" in MM.matches and "old00001" not in daemon.TEAM_SWAP, "old record without team_swap: no swap, no error")
# garbage values are ignored
rec2 = dict(rec, mid="bad00001", team_swap={T[0]: 5, "nobody": 1})
daemon._readopt_apply("bad00001", rec2, T[0], now)
check("bad00001" not in daemon.TEAM_SWAP, "invalid team / unknown token ignored")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
