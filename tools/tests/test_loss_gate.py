"""Packet loss limit (op 0xCA trailer 3 -> loss_note -> loss_check): a player whose median msg-7 loss across 2+ observers stays at or over
LOSS_KICK_PCT for LOSS_KICK_S is removed and his searches are held; a lossy host link (half or more lossy) removes nobody.
Run: python tools/tests/test_loss_gate.py"""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(n): return (n.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Host", "Lossy", "Ana", "Ben", "Cid"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0")
os.chdir(tempfile.mkdtemp())
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.evt = lambda *a, **k: None
MM = daemon.MM
H, L, A, B, C = T

def fnv(b):
    """The ext's hash (mem_probe.c trailer 3), written out here on purpose: a second implementation, not the daemon's."""
    h = 0x811C9DC5
    for c in b:
        h = ((h ^ c) * 0x01000193) % (1 << 32)
    return h

def payload(token, peers, alarm=False, fl=0):
    """An ext 0xCA report: v1 body, trailer 1, optional trailer 2, trailer 3 [(slot, name, rx, lost)]."""
    flags = 4 | (2 if alarm else 0)
    b = token.encode() + bytes([1, 0, 0, 0, 0, 160, 0, flags]) + bytes([1, 50, 0, 80, 0, 3, 3])
    if alarm:
        b += bytes([1, 6, 10, 0, 40, 0, 30])
    b += bytes([1, fl, len(peers)])
    for slot, nm, rx, lost in peers:
        b += bytes([slot]) + fnv(nm.encode("latin1")[:24]).to_bytes(4, "little") + rx.to_bytes(2, "little") + lost.to_bytes(2, "little")
    return b

# parser
p = daemon.parse_loss(payload(A, [(1, "Lossy", 900, 700), (0, "Host", 1700, 2)]))
check(p and p["peers"] == [(1, fnv(b"Lossy"), 900, 700), (0, fnv(b"Host"), 1700, 2)] and not p["paced"] and not p["hbw"], "trailer 3 parsed (%s)" % p)
p2 = daemon.parse_loss(payload(A, [(1, "Lossy", 900, 700)], alarm=True))
check(p2 and p2["peers"] == [(1, fnv(b"Lossy"), 900, 700)], "trailer 3 found after the alarm trailer (%s)" % p2)
old = payload(A, [])[:79]
old = old[:71] + bytes([0]) + old[72:]
check(daemon.parse_loss(old) is None, "an old ext report (no flag bit 2) = None")
check(daemon.parse_loss(payload(A, [(1, "Lossy", 1, 1)])[:-3]) is None, "a cut trailer = None")

def reset():
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "late_bonus"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear()
    daemon.LOSS.clear(); daemon.LOSS_HIGH.clear(); daemon.LOSS_KICKED.clear(); daemon.LOSS_HOLD.clear(); daemon.LOSS_FLAGS.clear()

def start(mid, players):
    MM.matches[mid] = list(players); MM.launched.add(mid); MM.started.add(mid); MM.formed[mid] = time.time() - 600

kicked = []
daemon.kick_token = lambda tok, *a, **k: (kicked.append(tok), ["kicked"])[1]

def report_all(now, lossy_pct, others_pct=0.0, players=(H, L, A, B, C), fl=None):
    for obs in players:
        peers = []
        for i, subj in enumerate(players):
            if subj == obs:
                continue
            pct = lossy_pct if subj == L else others_pct
            lost = int(1500 * pct / 100.0)
            peers.append((i, NAMES[T.index(subj)], 1500 - lost, lost))
        daemon.loss_note(obs, daemon.parse_loss(payload(obs, peers, fl=(fl or {}).get(obs, 0))), now)

# 1: one lossy player (44 %), the others clean -> timer, removal at 120 s; the 1st removal holds no search, a 2nd within 2 h does
reset(); kicked.clear(); daemon.LOSS_STRIKES.clear()
start("m1", [H, L, A, B, C])
t0 = time.time()
report_all(t0, 44.0)
check(daemon.loss_check(t0) == [] and (L, "m1") in daemon.LOSS_HIGH, "44 %% loss seen by 4: timer starts (%s)" % daemon.LOSS_HIGH)
check(not any(k[0] != L for k in daemon.LOSS_HIGH), "clean players get no timer")
for dt in (30, 60, 90):
    report_all(t0 + dt, 44.0)
check(daemon.loss_check(t0 + 90) == [], "not removed at 90 s")
report_all(t0 + 121, 44.0)
r = daemon.loss_check(t0 + 121)
check(r == [L] and kicked == [L], "removed at 121 s (%s)" % r)
check(daemon.loss_hold_note(L, t0 + 130) is None, "1st removal: searches again at once")
r = daemon.loss_check(t0 + 131)
check(r == [], "removed only once per match")
reset(); kicked.clear()                       # (LOSS_STRIKES survives: it is per player, not per match)
start("m1b", [H, L, A, B, C])
t1 = t0 + 1800
for dt in (0, 30, 60, 90, 121):
    report_all(t1 + dt, 44.0)
    daemon.loss_check(t1 + dt)
check(kicked == [L], "2nd removal 30 min later (%s)" % kicked)
note = daemon.loss_hold_note(L, t1 + 130)
check(note is not None and b"44%" in note and b"5 min" in note, "2nd removal within 2 h: next search held 5 min: %r" % note)
check(daemon.loss_hold_note(L, t1 + 121 + daemon.LOSS_HOLD_S + 1) is None, "hold over after LOSS_HOLD_S")
check(daemon.loss_hold_note(A, t1 + 130) is None, "a clean player is never held")

# 2: recovered under the limit -> timer cleared
reset(); kicked.clear()
start("m2", [H, L, A, B, C])
report_all(t0, 30.0)
daemon.loss_check(t0)
report_all(t0 + 30, 2.0)
daemon.loss_check(t0 + 100)           # window = only the 2 % report (the 30 % one is older than LOSS_WINDOW_S)
check((L, "m2") not in daemon.LOSS_HIGH, "back under: timer cleared")

# 3: everybody lossy (the host's link / relay) -> nobody judged
reset(); kicked.clear()
start("m3", [H, L, A, B, C])
report_all(t0, 44.0, others_pct=35.0)
daemon.loss_check(t0); report_all(t0 + 61, 44.0, others_pct=35.0)
r = daemon.loss_check(t0 + 61)
check(r == [] and not daemon.LOSS_HIGH, "all lossy: nobody removed (%s)" % r)

# 4: a single observer is not enough (2-player match)
reset(); kicked.clear()
start("m4", [H, L])
report_all(t0, 60.0, players=(H, L)); daemon.loss_check(t0); report_all(t0 + 61, 60.0, players=(H, L))
check(daemon.loss_check(t0 + 61) == [], "one observer: nobody removed")

# 5: too few packets in the window = unknown
reset(); kicked.clear()
start("m5", [H, L, A, B])
for obs in (H, A, B):
    daemon.loss_note(obs, {"paced": False, "hbw": False, "peers": [(1, fnv(b"Lossy"), 50, 60)]}, t0)
daemon.loss_check(t0)
check(not daemon.LOSS_HIGH, "under LOSS_MIN_PKTS: not judged")

# 6: duplicate names in a match: skipped
reset()
start("m6", [H, L, A])
real = daemon.get_name
daemon.get_name = lambda t: "Twin" if t in (L, A) else real(t)
daemon.loss_note(H, {"paced": False, "hbw": False, "peers": [(1, fnv(b"Twin"), 900, 700)]}, t0)
check(not daemon.LOSS, "an ambiguous name is not booked")
daemon.get_name = real

# 8: a recorded match: one at 34 %, the rest at 17-22 % (a lossy route for all) -> nobody judged
reset(); kicked.clear()
start("m8", [H, L, A, B, C])
for dt in (0, 30, 60, 90, 121):
    report_all(t0 + dt, 34.0, others_pct=19.0)
    daemon.loss_check(t0 + dt)
check(kicked == [] and not daemon.LOSS_HIGH, "rest of the match lossy too (19 %%): nobody removed (%s)" % kicked)

# 9: one at 40 %, the rest at 10 % (over LOSS_BASE_PCT, under half the limit) -> not judged
reset(); kicked.clear()
start("m9", [H, L, A, B, C])
for dt in (0, 30, 60, 90, 121):
    report_all(t0 + dt, 40.0, others_pct=10.0)
    daemon.loss_check(t0 + dt)
check(kicked == [], "rest of the match at 10 %%: not judged (%s)" % kicked)

# 7: log-only mode never removes
reset(); kicked.clear()
start("m7", [H, L, A, B, C])
daemon.LOSS_GATE = 1
report_all(t0, 44.0); daemon.loss_check(t0)
for dt in (30, 60, 90, 121): report_all(t0 + dt, 44.0)
check(daemon.loss_check(t0 + 121) == [] and kicked == [] and not daemon.LOSS_HOLD, "T2R_LOSS_GATE=1: logged, not removed")
daemon.LOSS_GATE = 2

# 7b: the lossy player paces his own sends (t2r-m7-lod.txt): not judged; a host budget in the match: nobody judged
for fl, what in (({L: 1}, "paced sender not judged"), ({H: 2}, "host upload budget on: match not judged")):
    reset(); kicked.clear()
    start("m7b", [H, L, A, B, C])
    report_all(t0, 44.0, fl=fl); daemon.loss_check(t0)
    check(not daemon.LOSS_HIGH, what)

# 7c: a long latin1 name is matched on its first 24 roster bytes
reset()
start("m7c", [H, L, A])
LONG = "Zoë the very long name of a player"
daemon.get_name = lambda t: LONG if t == L else real(t)
daemon.loss_note(H, daemon.parse_loss(payload(H, [(1, LONG.encode("latin1")[:24].decode("latin1"), 900, 700)])), t0)
check(len(daemon.LOSS) == 1, "long latin1 name matched on 24 roster bytes")
daemon.get_name = real

# 8: perf_op with the trailer still answers (never breaks the report)
reset()
start("m8", [H, L, A])
rep = daemon.perf_op(payload(A, [(1, "Lossy", 900, 700)]))
check(rep is not None and len(daemon.LOSS) == 1, "perf_op answers and books the trailer")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
