"""The ping table cap must not make a known pair ping unknown (a full table used to drop its first keys in insertion order, so a
joiner refused for its ping could join the same match seconds later).
Run: python tests/test_ping_cap.py"""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)
def tok(n):
    return ("%02x" % n) * 32
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8",
                  T2R_P2P="0", T2R_DB=os.path.join(tmp, "t2r.db"), T2R_PING_KICK_MS="190", T2R_PING_MAX="60")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "t2r.db"); daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.evt = lambda *a, **k: None
check(daemon.PING_MAX == 60, "T2R_PING_MAX sets the cap (60)")

SID = {}
def online(t):
    SID[t] = 76561198000000000 + len(SID)
    daemon.BRIDGES.register(t, object(), SID[t])
def report(a, b, ms):
    daemon.ping_report(a, SID[b], ms)

ON = [tok(i) for i in range(1, 9)]          # 8 online helpers = 56 directional pairs
for t in ON:
    online(t)
H, J = ON[0], ON[1]
report(J, H, 233); report(H, J, 233)        # inserted FIRST (the oldest keys of the table)
OFF = tok(0x40)
online(OFF)
for t in ON[2:4]:                           # pairs of a player who logs off: 4 directional pairs (56 + 4 = the cap of 60)
    report(OFF, t, 90); report(t, OFF, 90)
daemon.BRIDGES.unregister(OFF)
for a in ON:
    for b in ON:
        if a != b and {a, b} != {H, J}:
            report(a, b, 120)
for k in daemon.PING_AT:                    # (the reports above came minutes ago; one Windows clock tick otherwise)
    daemon.PING_AT[k] -= 120
report(J, H, 235); report(H, J, 235)        # the first pair keeps being refreshed
n0 = len(daemon.PING)
check(n0 == 60, "the table is at its cap before the next new pair (%d)" % n0)
# a new player comes online: new pairs push the table over the cap
NEW = tok(0x50)
online(NEW)
report(NEW, H, 70)
check(len(daemon.PING) <= daemon.PING_MAX, "the table stays within its cap (%d)" % len(daemon.PING))
check(not any(OFF in k for k in daemon.PING), "the offline player's pairs went out first")
check((J, H) in daemon.PING and (H, J) in daemon.PING, "the pair inserted first but reported recently is kept (the old rule dropped it)")
now = time.time()
check(daemon._ping_gate(J, H, now) == 235, "the gate still reads the joiner's ping to the host: %r" % daemon._ping_gate(J, H, now))

# the pair is gone from PING (evicted anyway): the gate falls back to PING_LAST and the join stays refused
for k in ((J, H), (H, J)):
    daemon.PING.pop(k, None); daemon.PING_AT.pop(k, None)
check(daemon._ping_gate(J, H, now) == 235, "evicted pair: the gate reads the last reported pair ping (%r)" % daemon._ping_gate(J, H, now))
blk = daemon.jip_ping_block(J, "m1", H, [H] + ON[2:5], [], now)
check(blk == 235, "join in progress after the eviction: refused at 235 ms, as 5 s earlier (got %r)" % blk)
check(daemon._ping_fresh(J, H, now) is None, "the in-match removal timer still reads PING only (no fresh ping)")
check(daemon._ping_gate(J, H, now + daemon.PING_GATE_AGE_S + 5) is None, "PING_LAST older than PING_GATE_AGE_S is unknown")
under = ON[2]
for k in ((under, H), (H, under)):
    daemon.PING.pop(k, None); daemon.PING_AT.pop(k, None)
check(daemon.jip_ping_block(under, "m1", H, [H, J], [], now) is None, "evicted pair under the limit (120 ms): joins")

# a connection / region change drops the player's pings, PING_LAST included
daemon._drop_pings(J)
check(not any(J in k for k in daemon.PING_LAST), "_drop_pings clears the player's PING_LAST pairs")
check(daemon._ping_gate(J, H, now) is None, "after a reset the pair is unknown (no old value)")

# gc_state prunes PING_LAST by age
daemon.PING_LAST[frozenset((tok(0x70), tok(0x71)))] = (300, now - daemon.PING_GATE_AGE_S - 60)
out = daemon.gc_state(now=now)
check(frozenset((tok(0x70), tok(0x71))) not in daemon.PING_LAST, "gc_state drops PING_LAST entries older than PING_GATE_AGE_S (%r)" % out.get("PING_LAST"))
check(frozenset((H, ON[3])) in daemon.PING_LAST, "gc_state keeps recent PING_LAST entries")

print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
