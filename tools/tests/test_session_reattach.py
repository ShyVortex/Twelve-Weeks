"""A session socket lost in a running match (a NAT dropped winmm's menu TCP socket 8.5 min into a match) must not end the match:
the match record stays, the same token re-attaches with login+hello (no match-start re-sent), a player who never returns is dropped after the grace,
a normal leave (0x02) and a plain menu announce are unaffected. Offline, temp DB, socketpair for the real tcp_conn close path.
Run: python tools/tests/test_session_reattach.py"""
import os, sys, tempfile, time, struct, socket, threading
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Erin", "Finn", "Gus"]
T = [tok(n) for n in NAMES]

os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_FILL_WAIT="0", T2R_P2P="0", T2R_HOST_MIGRATION="1", T2R_SESSION_GRACE="60")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
daemon.evt = lambda *a, **k: None
LOGS = []
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
daemon.threading.Timer = lambda *a, **k: type("NoTimer", (), {"start": lambda s: None, "daemon": True})()
MM, SESSIONS = daemon.MM, daemon.SESSIONS
with daemon._dblock, daemon.db() as c:
    for t in T:
        c.execute("INSERT OR IGNORE INTO players(token,name,matches,wins,draws,last_seen) VALUES(?,?,1,0,0,?)", (t, "x", time.time()))

def start_match(mid, players):
    now = time.time()
    with MM.lock:
        MM.matches[mid] = list(players); MM.formed[mid] = now - 120; MM.launched.add(mid); MM.started.add(mid); MM.started_t[mid] = now - 100
        MM.qtime[mid] = {}
    daemon.HM.start(mid, players)
    for t in players:
        daemon.CLAN_MATCH[t] = mid; daemon.LOADED.add(t); daemon.PRES.touch(t, "x")

def fr(op, pl=b""):
    return struct.pack("<H", len(pl) + 1) + bytes([op]) + pl
def login(t): return b"\x1c" + t.encode() + b"\x01\x02\x07"
def hello(name): return b"\x1c" + b"\x11" * 8 + name.encode().ljust(32, b"\x00")

class Rec:
    """a fake server-side conn: records what the daemon sends"""
    def __init__(s): s.out = []
    def sendall(s, b): s.out.append(bytes(b))
    def queued(s): return 0
    def close(s): pass
    def settimeout(s, x): pass

def new_st(): return {"token": None, "name": "PLAYER", "authed": False, "session": False, "is_bridge": False}
def attach(t, conn):
    st = new_st()
    daemon.handle_batch(conn, ("1.2.3.4", 5), st, [(0x0f, login(t)), (0x0e, hello(NAMES[T.index(t)]))])
    return st

# ---- (1) a session socket reset in a running match keeps the match
A, B, C, D, E, F, G = T
start_match("m1", [A, B, G])
ca, cb = Rec(), Rec()
SESSIONS.register(A, ca); SESSIONS.register(B, cb)
check(daemon.note_session_lost(A, ca), "reset in match: the loss is noted")
SESSIONS.unregister(A, ca)
check(MM.in_match(A) and MM.mid_of(A) == "m1", "match record and A's seat are kept after the reset")
check(A in daemon.SESS_LOST and daemon.SESS_LOST[A][1] == "m1", "the loss is remembered with the match id")
done = daemon.reap_matches(time.time())
check(MM.in_match(A) and MM.in_match(B) and not [d for d in done if d[0] == "m1"], "reaper inside the grace: nobody is dropped")

# ---- (2) reconnect re-attaches: session registered again, no match-start re-sent, match id / seat unchanged
ca2 = Rec()
st2 = attach(A, ca2)
check(SESSIONS.conn(A) is ca2, "re-attach registers the new socket as A's session")
check(st2["session"] and st2["started"] == "m1", "re-attached conn is a session of m1 (no match-start will be re-sent)")
check(A not in daemon.SESS_LOST, "loss record cleared")
check(len(ca2.out) == 1 and ca2.out[0][2:3] == b"\x10" and b"\x0d" not in [o[2:3] for o in ca2.out], "reply = name + lists, no 0x0d (the client stays)")
check(MM.mid_of(A) == "m1" and MM.players_of(A) == [A, B, G], "team / slot (players list) unchanged")
n_before = len(ca2.out)
daemon.handle_batch(ca2, ("1.2.3.4", 5), st2, [(0x05, b"")])
check(len(ca2.out) == n_before, "a keepalive after the re-attach sends nothing (no match-start re-sent)")
check(not daemon.note_session_lost(A, ca), "the old socket's late close is ignored (a newer session is registered)")
check(SESSIONS.conn(A) is ca2, "new session survives the old one's close")

# ---- (3) a player who never returns is dropped after the grace
SESSIONS.unregister(A, ca2)
daemon.SESS_LOST[A] = (time.time() - 10, "m1")
done = daemon.reap_matches(time.time())
check(MM.in_match(A), "10 s after the loss: still seated (grace 60 s)")
daemon.SESS_LOST[A] = (time.time() - 61, "m1")
done = daemon.reap_matches(time.time())
check(("m1", "session-lost:" + A) in done and not MM.in_match(A), "61 s after the loss: removed from the match (%s)" % done)
check(MM.in_match(B) and MM.in_match(G), "the other players play on")
check(A not in daemon.SESS_LOST, "loss record gone after the removal")

# ---- (3b) a player whose socket is gone while the level still loads holds the others up only LOAD_SESSION_GRACE_S, then they start
with daemon.MM.lock:
    MM.matches["m3"] = [E, F, G]; MM.formed["m3"] = time.time() - 60; MM.launched.add("m3"); MM.qtime["m3"] = {}
daemon.HM.start("m3", [E, F, G])
for t in (E, F): daemon.LOADED.add(t); daemon.PRES.touch(t, "x")
daemon.PRES.touch(G, "x"); daemon.LOADED.discard(G)
daemon.SESS_LOST[G] = (time.time() - 10, "m3")
daemon.reap_matches(time.time())
check(MM.in_match(G) and "m3" not in MM.started, "10 s after the loss of an unloaded player: still waiting")
daemon.SESS_LOST[G] = (time.time() - 16, "m3")
done = daemon.reap_matches(time.time())
check(("m3", "session-lost:" + G) in done and not MM.in_match(G), "16 s after the loss of an unloaded player: removed (%s)" % done)
check("m3" in MM.started, "the loaded players are started at once (GAME-START)")

# ---- (4) normal leave unaffected: 0x02 frees the player, no loss record, a later announce is a plain menu announce
start_match("m2", [C, D])
cc = Rec(); SESSIONS.register(C, cc)
stC = new_st(); stC.update(token=C, session=True, menu=True, authed=True, started="m2")
daemon.handle_leave(("1.2.3.4", 6), stC)
check(not MM.in_match(C), "0x02 leave: C is out of the match")
check(C not in daemon.SESS_LOST, "leave leaves no loss record")
SESSIONS.unregister(C, cc)
check(not daemon.note_session_lost(C, cc), "closing the socket of a player who left is not a loss")
stc2 = attach(C, Rec())
check(not stc2["session"] and stc2["authed"], "announce after a leave: a plain menu socket, not a session")

# ---- (5) an ordinary menu announce of a player in a running match with NO loss is not a re-attach
start_match("m3", [A, C])
st5 = attach(A, Rec())
check(not st5["session"], "announce without a loss record is not a re-attach")
with MM.lock:
    MM.matches.pop("m3", None); MM.launched.discard("m3")

# ---- (6) the real tcp_conn path: a socket re-attaches (login+hello after a loss), then it closes in the running match and the loss is recorded again
daemon.SESS_LOST.clear()
start_match("m6", [E, F])
daemon.SESS_LOST[E] = (time.time() - 3, "m6")
a, b = socket.socketpair()
thr = threading.Thread(target=daemon.tcp_conn, args=(b, ("9.9.9.9", 9)), daemon=True); thr.start()
a.sendall(fr(0x0f, login(E)) + fr(0x0e, hello("Erin")))
time.sleep(1.0)
check(SESSIONS.conn(E) is not None and E not in daemon.SESS_LOST, "tcp_conn: login+hello after a loss re-attached (%s)" % [l for l in LOGS if "REATTACH" in l][-1:])
a.close(); thr.join(5)
check(MM.in_match(E) and E in daemon.SESS_LOST and SESSIONS.conn(E) is None,
      "tcp_conn: the session socket closing in a running match keeps the seat and records the loss (%s)" % [l for l in LOGS if "SESSION conn closed" in l][-1:])

print("%d failed" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
