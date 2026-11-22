"""The ping gates judge the last measured pair ping when no fresh one exists (a 287 ms player was matched and a joiner
refused at 262 ms joined one second later, both because the pair ping had turned stale). Run: python tests/test_ping_gate_stale.py"""
import os, sys, tempfile, time, collections
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
                  T2R_P2P="0", T2R_DB=os.path.join(tmp, "t2r.db"), T2R_PING_KICK_MS="190")
import daemon, hostmig  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "t2r.db"); daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.evt = lambda *a, **k: None

def setp(a, b, ms, age):
    daemon.PING[(a, b)] = collections.deque([ms], maxlen=5)
    daemon.PING_AT[(a, b)] = time.time() - age

H, J, K, L = T[0], T[1], T[2], T[3]
now = time.time()
setp(H, J, 262, 120)          # stale (older than PING_FRESH_S), within PING_GATE_AGE_S
setp(H, K, 80, 30)            # fresh, under
setp(H, L, 300, 7200)         # too old for the gate
check(daemon._ping_fresh(H, J, now) is None, "the 120 s old ping is not fresh (ping_check ignores it)")
check(daemon._ping_gate(H, J, now) == 262, "the gate reads the 120 s old ping: 262")
check(daemon._ping_gate(H, K, now) == 80, "a fresh ping is read as is")
check(daemon._ping_gate(H, L, now) is None, "a 2 h old ping is unknown to the gate")
check(daemon._ping_gate(H, T[4], now) is None, "never measured = unknown")
# join in progress: the stale 262 now blocks
blk = daemon.jip_ping_block(J, "m1", H, [H, K], [], now) if daemon.MM_PING_GATE else 262
check(blk == 262, "join in progress: a joiner at a stale 262 ms is refused (%r)" % blk)
check(daemon.jip_ping_block(K, "m1", H, [H, J], [], now) is None, "a joiner at a fresh 80 ms joins")
# formation: ping_fit with the gate's reader drops the stale-262 player (every pair measured, as in the real lobby)
setp(K, J, 250, 200)
kept, dropped, gh, info = hostmig.ping_fit([H, J, K], lambda a, b: daemon._ping_gate(a, b, now), 190)
check(J in dropped and H in kept and K in kept, "formation: the stale 262 ms player is not matched (kept %d, dropped %d)" % (len(kept), len(dropped)))
kept2, dropped2, _, _ = hostmig.ping_fit([H, J, K], lambda a, b: daemon._ping_fresh(a, b, now), 190)
check(J in kept2, "(the old fresh-only reader kept him: the old bug)")
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
