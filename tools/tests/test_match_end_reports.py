"""Match end without the host's op 0x12 (re/match-end-fallback-1019.md): the daemon closes the match from the clients' 0xE2 end-reports (flags bit 1),
never double-closes with a late 0x12, never closes a match somebody still plays (JIP joiner, a player that did not report), and every ext request
refreshes presence. Offline, temp DB, no sockets.  Run: python tools/tests/test_match_end_reports.py"""
import os, sys, tempfile, time, struct
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
T = [tok(n) for n in NAMES]

os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_FILL_WAIT="0", T2R_P2P="0", T2R_HOST_MIGRATION="1", T2R_MEND_GRACE="8")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
daemon.evt = lambda *a, **k: None
MM = daemon.MM
LOGS = []
_log = daemon.log
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
daemon.threading.Timer = lambda *a, **k: type("NoTimer", (), {"start": lambda s: None, "daemon": True})()   # no real 9 s / grace timers

def fresh():
    with daemon._dblock, daemon.db() as c:
        for t in T:
            c.execute("INSERT OR IGNORE INTO players(token,name,matches,wins,draws,last_seen) VALUES(?,?,1,0,0,?)", (t, "x", time.time()))
            c.execute("UPDATE players SET wins=0, draws=0 WHERE token=?", (t,))

def start_match(mid, players):
    now = time.time()
    with MM.lock:
        MM.matches[mid] = list(players); MM.formed[mid] = now - 120; MM.launched.add(mid); MM.started.add(mid); MM.started_t[mid] = now - 100
        MM.qtime[mid] = {}
    daemon.HM.start(mid, players)
    for t in players:
        daemon.CLAN_MATCH[t] = mid; daemon.LOADED.add(t); daemon.PRES.touch(t, "x")

def wins(t):
    with daemon._dblock, daemon.db() as c:
        r = c.execute("SELECT wins, draws FROM players WHERE token=?", (t,)).fetchone()
    return tuple(r)

def report(t, flags):
    daemon.clan_report(t, 10, flags)

def ended(mid):
    return mid in MM.ended

fresh()
# ---- (1) all report the end, no 0x12: closed after the grace
MID = "m1000001"; PL = T[:3]
start_match(MID, PL)
report(PL[0], 2)
check(not ended(MID), "one of three reported: match stays live")
check(daemon.match_end_via_reports(MID) is False, "...and an immediate call does nothing (not everybody, grace)")
report(PL[1], 2)
report(PL[2], 2)
check(daemon.match_end_via_reports(MID, time.time()) is False, "all reported but inside the MEND_GRACE: the host's 0x12 gets its chance")
check(daemon.match_end_via_reports(MID, time.time() + 9.0) is True, "all reported, grace over: closed")
check(ended(MID) and MID in daemon.CLAN_ENDED, "MM.ended + CLAN_ENDED set")
check(any("MATCH-END via client reports" in l for l in LOGS), "log line 'MATCH-END via client reports'")
check(all(wins(t) == (0, 0) for t in PL), "no win / draw credited (winner unknown)")
check(daemon.match_end_via_reports(MID, time.time() + 20) is False, "second call: idempotent")
n_logs = sum("MATCH-END via client reports" in l for l in LOGS)
# ---- (2) a late 0x12 books the winner, closes nothing twice
winner = 0 if daemon.team_of(0) == 0 else 1
st = {"token": PL[0]}
ce_before = daemon.CLAN_ENDED[MID]
daemon.handle_match_end(("1.2.3.4", 1), st, [(0x12, bytes([winner]))])
check(any("after the client-report close" in l for l in LOGS), "late 0x12 after the fallback close: acknowledged as late")
check(daemon.CLAN_ENDED[MID] == ce_before, "late 0x12 did not re-run clan_match_ended")
w = [wins(t)[0] for t in PL]
check(sum(w) >= 1, "late 0x12 credits the winning team (%s)" % w)
daemon.handle_match_end(("1.2.3.4", 1), st, [(0x12, bytes([winner]))])
check([wins(t)[0] for t in PL] == w, "a repeated 0x12 books nothing twice")
check(sum("MATCH-END via client reports" in l for l in LOGS) == n_logs, "no second fallback close")

# ---- (3) 0x12 first, then the reports: fallback does nothing
fresh()
MID = "m1000002"; PL = T[:3]
for t in PL: daemon.CLAN_REPORTED_END.pop(MID, None)
start_match(MID, PL)
daemon.handle_match_end(("1.2.3.4", 1), {"token": PL[0]}, [(0x12, bytes([2]))])
check(ended(MID), "0x12 closes the match as before")
for t in PL: report(t, 2)
check(daemon.match_end_via_reports(MID, time.time() + 30) is False, "reports after the 0x12: fallback no-op")
check(not any("MID" in l and "client reports" in l for l in LOGS[-3:]), "no fallback log after a normal 0x12")

# ---- (4) one player did not report and is still present: never close
MID = "m1000003"; PL = T[3:6]
start_match(MID, PL)
report(PL[0], 2); report(PL[1], 2)
check(daemon.match_end_via_reports(MID, time.time() + 30) is False, "a present player has not reported: match still being played")
# the third goes silent (crashed host): ignored once silent > OFFLINE_GRACE
with daemon.PRES.lock: daemon.PRES.players[PL[2]]["last"] = time.time() - daemon.OFFLINE_GRACE - 5
check(daemon.match_end_via_reports(MID, time.time() + 30) is True, "the non-reporter is silent (crashed): the rest closes the match")

# ---- (5) departed players do not count; a JIP joiner still loading blocks
MID = "m1000004"; PL = T[:3]
daemon.CLAN_ENDED.pop("m1000004", None)
start_match(MID, PL)
with MM.lock: MM.departed.setdefault(MID, set()).add(PL[2])
report(PL[0], 2); report(PL[1], 2)
with MM.lock: MM.joining[T[5]] = (MID, time.time())
check(daemon.match_end_via_reports(MID, time.time() + 30) is False, "JIP joiner not started yet: not closed")
with MM.lock: MM.joining.clear()
check(daemon.match_end_via_reports(MID, time.time() + 30) is True, "departed player ignored, joiner gone: closed")

# ---- (6) match not started / a left-early report (bit 0 only) never closes
MID = "m1000005"; PL = T[:2]
start_match(MID, PL)
with MM.lock: MM.started.discard(MID)
report(PL[0], 2); report(PL[1], 2)
check(daemon.match_end_via_reports(MID, time.time() + 30) is False, "never-started match is not closed by reports")
MID = "m1000006"
start_match(MID, T[:2])
report(T[0], 1); report(T[1], 1)
check(daemon.match_end_via_reports(MID, time.time() + 30) is False, "reports without flags bit 1 (left early) do not close")

# ---- (7) the reaper drives it
MID = "m1000007"; PL = T[:2]
start_match(MID, PL)
with daemon._clanlock: daemon.CLAN_REPORTED_END[MID] = {PL[0]: time.time() - 20, PL[1]: time.time() - 20}
done = daemon.reap_matches(time.time())
check((MID, "end-reports") in done and ended(MID), "reap_matches closes it (%s)" % [d for d in done if d[0] == MID])

# ---- (8) presence: every ext request with a token refreshes PRES (and never creates a player)
ghost = tok("Zed")
class _C:
    def sendall(self, b): pass
for op, extra in ((0xE0, b""), (0xBA, b"\x01\x00"), (0xDE, b"\x00"), (0xCA, b"\x01" + b"\x00" * 9), (0xE4, b"\x01")):
    t = T[1]
    with daemon.PRES.lock: daemon.PRES.players[t]["last"] = time.time() - 90
    try:
        daemon.handle_batch(_C(), ("9.9.9.9", 1), {"token": None, "name": "PLAYER", "authed": False, "session": False, "is_bridge": False},
                            [(op, t.encode("latin1") + extra)])
    except Exception as e:                                           # noqa: BLE001 - the reply path may need more state; presence is touched first
        pass
    check(daemon.silence(t, time.time()) < 5, "op 0x%02x refreshes presence" % op)
daemon.handle_batch(_C(), ("9.9.9.9", 1), {"token": None, "name": "PLAYER", "authed": False, "session": False, "is_bridge": False},
                    [(0xE6, ghost.encode("latin1") + b"\x00\x00")])
check(ghost not in daemon.PRES.players, "an unknown token is not created by presence")

# ---- (7) a 0x12 that is mid-close (RESULT_BOOKED set, MM.ended not yet) is never raced by the fallback timer
MID = "m1000007"; PL = T[:2]
start_match(MID, PL)
report(PL[0], 2); report(PL[1], 2)
daemon.RESULT_BOOKED.add(MID)
check(daemon.match_end_via_reports(MID, time.time() + 30) is False, "result already booked (0x12 closing on another thread): fallback stands down")
daemon.RESULT_BOOKED.discard(MID)

print("\nall passed" if not FAILS else "\n%d FAILED" % len(FAILS))
sys.exit(1 if FAILS else 0)
