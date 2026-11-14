"""Offline tests for the per-mode queues (tools/modeq.py): picks, grouping into one mode per match, party leader's mode, JIP fit, T2R_MODE forcing,
the op 0xBC payload. Run: python tools/tests/test_modeq.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import modeq  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def tok(c):
    return c * 64


os.environ.pop("T2R_MODE", None)
q = modeq.ModeQ(now=lambda: 1000.0)
A, B, C, D, E = (tok(c) for c in "abcde")
none = lambda t: None  # noqa: E731
check(q.get(A) == 0, "no pick = supply raid")
q.set(A, 1); q.set(B, 1); q.set(C, 0)
check(q.counts([A, B, C, D], none) == [2, 2], "counts per mode (D has no pick = supply raid)")
r, m = q.group([C, A, B], none)
check(r == [A, B] and m == "interrogation", "group = the first mode with >= 2 players (C alone is skipped)")
r, m = q.group([C, D, A], none)
check(r == [C, D] and m == "supply-raid", "group = supply raid pair")
r, m = q.group([A], none)
check(r == [A] and m == "interrogation", "a lone searcher keeps its own mode (so the wait logic runs)")
check(q.get(D, A) == 1, "a party member searches in its leader's mode")
q.formed("m1", "interrogation")
check(not q.fits(C, "m1") and q.fits(A, "m1") and q.fits(E, "m2"), "join in progress only into a match of the same mode (unknown match = ok)")
check(q.match_mode("m1") == "interrogation", "match mode recorded")
check(not q.set(A, 2) and q.get(A) == 1, "a bad mode is refused")
check(modeq.ModeQ.parse(tok("a").encode() + bytes([1, 1])) == (tok("a"), 1, 1), "op payload parsed")
check(modeq.ModeQ.parse(b"short") is None, "short payload refused")
os.environ["T2R_MODE"] = "interrogation"
r, m = q.group([C, A, B], none)
check(m is None and r == [C, A, B] and q.fits(C, "m1") and q.match_mode("m1") is None, "T2R_MODE forces: no grouping, no mode override")
os.environ.pop("T2R_MODE")
check(modeq.ModeQ.reply([2, 3], 1, False) == "q0=2 q1=3 mode=1 forced=0 any=1 qa=5", "reply text")
check(modeq.ModeQ.reply([1, 1], modeq.ANY, False, 1) == "q0=1 q1=1 mode=2 forced=0 any=1 qa=1", "ANY is reported as the QUICK MATCH row (= NMODES)")

# ---- QUICK MATCH (ANY)
Q = modeq.ModeQ(now=lambda: 1000.0)
ANY = modeq.ANY
for t, m in ((A, ANY), (B, ANY), (C, 0), (D, 1), (E, 1)):
    check(Q.set(t, m), "set %s" % m)
check(Q.counts([A, B, C, D, E], none) == [3, 4], "ANY counts in every mode")
r, m = Q.group([A, C, D, E], none)
check(r == [A, D, E] and m == "interrogation", "ANY joins the mode that already has most players (2 interrogation vs 1 supply raid)")
r, m = Q.group([A, B], none)
first = m
r2, m2 = Q.group([A, B], none)
check(set(r) == {A, B} and m != m2, "two ANY searchers form a lobby and the mode rotates (%s, %s)" % (first, m2))
r, m = Q.group([A, C], none)
check(r == [A, C] and m == "supply-raid", "ANY + one specific = their lobby")
r, m = Q.group([A], none)
check(r == [A] and m in modeq.MODES, "a lone ANY keeps waiting in a valid mode")
r, m = Q.group([C, A, D], none)
check(set(r) == {C, A} and m == "supply-raid", "tie on players: the oldest waiting specific wins, ANY follows, the other mode waits")
Q.formed("m9", "interrogation")
check(Q.fits(A, "m9") and not Q.fits(C, "m9"), "ANY fits any running match (JIP), specific only its own")
check(Q.get(B, A) == ANY, "a party member follows a leader who picked ANY")
check(modeq.ModeQ.compat(ANY, 0) and modeq.ModeQ.compat(1, ANY) and not modeq.ModeQ.compat(0, 1), "search page list compat")
check(not Q.set(A, 7) and Q.get(A) == ANY, "an unknown mode still refused (old-daemon behaviour: client falls back)")
# old client / old daemon contract: specific picks behave exactly as before
check(modeq.ModeQ.parse(tok("a").encode() + bytes([1, 255])) == (tok("a"), 1, 255), "ANY on the wire = 255")


# ---- the real MatchMaker.try_form (daemon): four searchers, two per mode -> two matches, each of one mode
import tempfile, time  # noqa: E402
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
T = [tok(c) for c in "wxyz"]
daemon.get_name = lambda t: t[:4]
daemon.tag = lambda t: t[:4]
daemon.log = lambda *a, **k: None
for t in T: daemon.PRES.touch(t, "x")
MM = daemon.MM
now = time.time()
for i, t in enumerate(T):
    MM.queue[t] = now - 10 - i; MM.seen[t] = now; MM.settle[t] = 0
daemon.MODEQ.set(T[0], 1); daemon.MODEQ.set(T[1], 0); daemon.MODEQ.set(T[2], 1); daemon.MODEQ.set(T[3], 0)
MM.last_arrival = 0
mid, pl = MM.try_form()
check(mid is not None, "try_form returns a match")
modes = {frozenset(pl): daemon.MODEQ.match_mode(mid)}
check(set(pl) in ({T[0], T[2]}, {T[1], T[3]}), "the first match has players of ONE mode only: %s" % [t[:1] for t in pl])
check(daemon.MODEQ.match_mode(mid) == ("interrogation" if set(pl) == {T[0], T[2]} else "supply-raid"), "the match mode is that group's mode")
mid2, pl2 = MM.try_form()
check(mid2 is None or set(pl2) in ({T[0], T[2]}, {T[1], T[3]}), "no mixed match from the rest")

# ---- tools/modes.json is the one list: modeq, the ext header and the widget page agree
import gen_modes  # noqa: E402
check(modeq.MODES == tuple(e["key"] for e in gen_modes.load()), "modeq.MODES = tools/modes.json")
check(open(os.path.join(os.path.dirname(HERE), "ext", "modes.h"), newline="").read() == gen_modes.header(), "tools/ext/modes.h is generated from modes.json (run python tools/gen_modes.py)")
check(modeq.ModeQ.reply([1, 2, 3], 2, True) == "q0=1 q1=2 q2=3 mode=2 forced=1 any=1 qa=6", "reply has one q per mode")
print("FAILED: %s" % FAILS if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
