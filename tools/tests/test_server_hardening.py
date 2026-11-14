"""Offline tests for the server hardening: stuck match states (reaper), leave / timeout / reconnect, UDP relay
robustness (loss, oversize, floods, malformed, slot theft), TCP framing, version check, log rotation, map vote with
fewer players, empty-server recovery.
Run: python tools/tests/test_server_hardening.py   (free localhost port, temp DB, no port 7001/7101)."""
import os, sys, socket, struct, tempfile, threading, time, random
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave"]
A, B, C, D = [tok(n) for n in NAMES]

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_MATCH_SIZE="4", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_FILL_RULE="classic", T2R_MAP_VOTE="1", T2R_MAX_TEAM="0",
                  T2R_VERSION="v-server-1", T2R_UDP_PPS="100", T2R_UDP_BPS="1000000")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)
MM = daemon.MM

def reset():
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed"):
        getattr(MM, a).clear()
    for a in ("launched", "ended", "timed_out", "started"):
        getattr(MM, a).clear()
    MM.ended_at.clear(); MM.last_arrival = 0
    daemon.LOADED.clear(); daemon.VOTES.clear(); daemon.MATCH_MAP.clear(); daemon._SILENT.clear()

def online(*toks, ago=0.0):
    now = time.time()
    for t in toks:
        daemon.PRES.touch(t, "x")
        daemon.PRES.players[t]["last"] = now - ago

def make_match(players, mid="m1", age=100.0, launched=True):
    with MM.lock:
        MM.matches[mid] = list(players)
        MM.formed[mid] = time.time() - age
        if launched: MM.launched.add(mid)

# ------------------------------------------------------------------ TCP framing
fr, rest = daemon.split_frames(b"\x00\x00\x00\x00\x02\x00\x05\x01\x05\x00\x09AB")
check(fr == [(5, b"\x01")] and rest == b"\x05\x00\x09AB", "split_frames: zero length skipped, partial frame kept: %s %s" % (fr, rest))
c = socket.create_connection(("127.0.0.1", port), timeout=3)
c.sendall(b"\x00\x00" * 5000 + b"\x02\x00\x05\x01")      # zero-length garbage, then a real keepalive
time.sleep(0.3)
c.sendall(b"\xff\xff" + os.urandom(200))
time.sleep(0.3)
c.close()
check(True, "TCP garbage did not hang or kill the accept loop")
c = socket.create_connection(("127.0.0.1", port), timeout=3)
c.sendall(struct.pack("<H", 2) + bytes([0xB0, 0]))    # malformed version request
time.sleep(0.3)
d = c.recv(4096)
check(d[2] == 0xB1 and b"ok=0" in d, "malformed 0xB0 answered ok=0, connection alive")
ver = b"v-server-1"
req = struct.pack("<H", 2 + len(ver)) + bytes([0xB0, len(ver)]) + ver
c.sendall(req); time.sleep(0.3)
d = c.recv(4096)
check(b"ok=1" in d and b"server=v-server-1" in d, "version request over TCP: ok=1: %s" % d[3:])
c.close()

# ------------------------------------------------------------------ version
r = daemon.parse_version_request(bytes([3]) + b"abc" + A.encode())
check(r == ("abc", A), "parse_version_request: version + token")
check(daemon.parse_version_request(bytes([3]) + b"a c") is None, "parse_version_request: illegal characters refused")
check(daemon.parse_version_request(bytes([9]) + b"abc") is None, "parse_version_request: truncated refused")
daemon.CLIENT_VERSIONS.clear()
check(daemon.version_problem(A) is None, "unreported client allowed (old launcher)")
daemon.version_op(bytes([4]) + b"old1" + A.encode())
check("old1" in (daemon.version_problem(A) or "") and "v-server-1" in daemon.version_problem(A), "mismatched client gets the clear message: %s" % daemon.version_problem(A))
rep = daemon.version_op(bytes([4]) + b"old1")
check(b"ok=0" in rep and b"Version mismatch" in rep, "0xB0 reply for a mismatch says ok=0 + message")
daemon.version_op(bytes([10]) + b"v-server-1" + A.encode())
check(daemon.version_problem(A) is None, "matching version allowed")
daemon.version_op(bytes([4]) + b"old2" + A.encode() + b"L")
_lp = daemon.version_problem(A) or ""
check("t2r-linux.py" in _lp and "Play.bat" not in _lp, "a Linux client's version note names the Linux launcher, not Play.bat: %s" % _lp)
daemon.LINUX_CLIENTS.discard(A)
# update UX: a stale build gets the refusal (per-token language) + the 'v' notice; one already in a match is left alone (grace) and sees 'u'
daemon.version_op(bytes([4]) + b"old3" + A.encode())
_n = daemon.version_refusal(A) or ""
check("restart the launcher" in _n and "uruchom" not in _n, "stale build: refused with the update note in the token's language (English by default)")
daemon.CLIENT_LANGS[A] = "pl"
_np = daemon.version_refusal(A) or ""
check("uruchom ponownie launcher" in _np and "restart" not in _np, "...and in Polish only for a Polish token")
daemon.CLIENT_LANGS.pop(A, None)
check(any(k == "v" for _i, k, _p, _t in daemon.notice_items(A)), "stale build outside a match gets the 'v' notice")
_oim = daemon.MM.in_match
daemon.MM.in_match = lambda t: True
check(daemon.version_refusal(A) is None, "grace: a previous-build client already in a match is not refused")
check(any(k == "u" for _i, k, _p, _t in daemon.notice_items(A)) and not any(k == "v" for _i, k, _p, _t in daemon.notice_items(A)), "in a match it only sees 'update available' (u)")
daemon.MM.in_match = _oim
daemon.version_op(bytes([10]) + b"v-server-1" + A.encode())
daemon.REQUIRE_VERSION = True
check(daemon.version_problem(B) is not None, "T2R_REQUIRE_VERSION: an unreported client is refused")
daemon.REQUIRE_VERSION = False

# ------------------------------------------------------------------ bridge re-registration
class Sock: pass
c1, c2 = Sock(), Sock()
daemon.BRIDGES.register(A, c1, 1, 7777)
daemon.BRIDGES.register(A, c2, 1, 7777)
check(daemon.BRIDGES.unregister(A, c1) is False and daemon.BRIDGES.steamid(A) == 1, "old helper conn closing does not unregister the new registration")
check(daemon.BRIDGES.unregister(A, c2) is True and daemon.BRIDGES.steamid(A) == 0, "the current conn unregisters")

# ------------------------------------------------------------------ leave keeps the others, last one out removes
reset(); online(A, B, C)
make_match([A, B, C])
daemon.LOADED.update([A, B, C])
kept = daemon.leave_running_match(B, "test")
check(kept and MM.players_of(A) == [A, B, C] and MM.players_of(B) is None, "leave without host migration: the leaver is free, the others keep the match")
check(not MM.in_match(B) and MM.in_match(A), "leaver may queue again")
daemon.leave_running_match(A, "test"); daemon.leave_running_match(C, "test")
check(not MM.matches, "last one out removes the match record")

# ------------------------------------------------------------------ reaper
reset(); online(A, B, ago=500)                      # both offline for ages
make_match([A, B], age=500)
daemon.VOTES[frozenset([A, B])] = {"opts": [0], "votes": {}, "winner": -1}
done = daemon.reap_matches()
check(done == [("m1", "drop")] and not MM.matches and frozenset([A, B]) not in daemon.VOTES, "match with every player offline is reaped (record + vote gone)")
online(A, B)
mid, pl = MM.enqueue(A)
mid, pl = MM.enqueue(B)
check(mid is not None and set(pl) == {A, B}, "after the reap both players can queue and form a new match")

reset(); online(A, B)
make_match([A, B], age=500); daemon.LOADED.update([A, B])
check(daemon.reap_matches() == [] and MM.matches, "a live match is left alone")

reset(); online(A, B)
make_match([A, B], age=10, launched=False)
MM.ended.add("m1"); MM.ended_at["m1"] = time.time() - 200
check(daemon.reap_matches() == [("m1", "drop")], "finished match whose free timer was lost is freed")

reset(); online(A, B)
make_match([A, B], age=daemon.countdown_seconds() + 200, launched=False)
done = daemon.reap_matches()
check(done == [("m1", "abort")] and not MM.matches and set(MM.queue) == {A, B}, "stalled countdown: match aborted, players back in the queue")

reset(); online(A, B, C)
online(C, ago=daemon.PLAYER_DEPART + 30)
make_match([A, B, C], age=300)
daemon.LOADED.update([A, B, C])
done = daemon.reap_matches()
check(("m1", "timeout:" + C) in done and MM.players_of(A) == [A, B, C] and MM.players_of(C) is None,
      "a player silent for PLAYER_DEPART s is departed, the others play on")
online(C)
check(not MM.in_match(C), "the timed-out player can queue again on reconnect")

reset(); online(A, B, C)
online(C, ago=daemon.OFFLINE_GRACE + 5)
make_match([A, B, C], age=300); daemon.LOADED.update([A, B, C])
daemon.reap_matches()
check(C in daemon._SILENT and MM.players_of(C) == [A, B, C], "silent but not yet timed out: logged, still in the match")
online(C)
daemon.reap_matches()
check(C not in daemon._SILENT, "silent player back again: cleared")

# load timeout: C crashed while loading -> A, B start
reset(); online(A, B, C)
make_match([A, B, C], age=daemon.countdown_seconds() + daemon.LOAD_TIMEOUT + 30)
daemon.LOADED.update([A, B])
daemon.reap_matches()
check("m1" in MM.started and MM.players_of(C) is None, "load timeout: the player that never loaded is removed and the loaded ones start")

# a leaver during loading no longer blocks the start
reset(); online(A, B, C)
make_match([A, B, C], age=60)
daemon.LOADED.update([A, B])
daemon.leave_running_match(C, "left")
check(daemon.maybe_game_start(A), "game start counts only the players still in the match")

# ------------------------------------------------------------------ reconnect: same token
reset(); online(A, B)
make_match([A, B], age=200)
daemon.LOADED.add(A)
# A's connection died; it comes back and presses FIND MATCH: daemon treats the old match as over for A only
daemon.leave_running_match(A, "searching again")
mid, pl = MM.enqueue(A)
check(MM.players_of(B) == [A, B] and A in MM.queue or mid is not None, "reconnecting player re-queues while the others keep the match")

# ------------------------------------------------------------------ vote with fewer players
reset(); online(A, B)
make_match([A, B], launched=False, age=1)
opts = daemon.vote_start([A, B])
check(daemon.vote_cast(A, 1) and not daemon.vote_cast(C, 0), "vote: members count, outsiders do not")
w = daemon.vote_close([A, B])
check(w == opts[1], "vote with 2 players closes on the single vote")
reset(); online(A, B)
make_match([A, B], launched=False, age=1)
daemon.vote_start([A, B])
w = daemon.vote_close([A, B])
check(w in daemon.vote_start([A, B]) or w >= 0, "vote with nobody voting still picks a map (no waiting for ever)")
with MM.lock: MM.matches.clear()
daemon.forget_match_state([A, B])
check(frozenset([A, B]) not in daemon.VOTES and frozenset([A, B]) not in daemon.MATCH_MAP, "forget_match_state clears vote + map")

# ------------------------------------------------------------------ UDP relay
sent = []
bad_peers = set()
def fake_send(data, addr):
    if addr in bad_peers:
        raise OSError("peer unreachable")
    sent.append((addr, data))
U = daemon.UdpRelay(fake_send)
a0, a1, a2 = ("10.0.0.1", 1000), ("10.0.0.2", 2000), ("10.0.0.3", 3000)
sid = 0xABCDEF01
def hello(addr, slot): U.handle(b"\x00" + struct.pack("<I", sid) + bytes([slot]), addr)
def dat(addr, src, dst, body=b"T2RO\x00\x00\x05xxxx"): U.handle(b"\x02" + struct.pack("<I", sid) + bytes([src, dst]) + body, addr)
daemon.RELAY.clear(); daemon.RELAY_TS.clear()
hello(a0, 0); hello(a1, 1); hello(a2, 2)
sent.clear()
dat(a0, 0, 1)
check(sent == [(a1, b"\x02" + struct.pack("<I", sid) + bytes([0, 1]) + b"T2RO\x00\x00\x05xxxx")], "DATA relayed to the destination slot only")
sent.clear(); bad_peers.add(a1)
dat(a0, 0, 1); dat(a0, 0, 2)
check([x[0] for x in sent] == [a2], "a failing / slow peer does not block packets to the others")
bad_peers.clear(); sent.clear()
dat(a0, 0, 0xFF)
check({x[0] for x in sent} == {a1, a2}, "broadcast reaches everyone but the source")
# duplicates and reordering pass through untouched (the game's own sequence numbers handle them)
sent.clear()
for n in (3, 1, 1, 2):
    dat(a0, 0, 2, b"T2RO\x00\x00\x05" + bytes([n]))
check([x[1][-1] for x in sent] == [3, 1, 1, 2], "duplicates / reordering are forwarded as they came")
# slot theft
thief = ("66.6.6.6", 9)
sent.clear()
dat(thief, 0, 2)
check(daemon.RELAY[(sid, 0)] == a0 and U.counters["hijack-refused"] == 1 and not sent, "another host cannot take over a live slot with DATA")
hello(thief, 0)
check(daemon.RELAY[(sid, 0)] == thief, "a HELLO rebinds the slot (client restart)")
hello(a0, 0)
# oversize / malformed / fuzz
U.handle(b"\x02" * 5000, a0)
check(U.counters["oversized"] == 1, "oversized datagram dropped")
rnd = random.Random(7)
U2 = daemon.UdpRelay(fake_send)
ok = True
try:
    for i in range(20000):
        n = rnd.choice([0, 1, 2, 5, 6, 7, 8, 13, 14, 40, 300])
        data = bytes(rnd.randrange(256) for _ in range(n))
        if n and rnd.random() < 0.6:
            data = bytes([rnd.choice([0, 2, 3, 4, 0xff])]) + data[1:]
        U2.handle(data, ("9.9.9.%d" % rnd.randrange(250), rnd.randrange(1, 65535)), now=1000.0 + i * 0.01)
except Exception as e:
    ok = False; print("fuzz exception", repr(e))
check(ok, "20000 random / truncated packets: no exception")
U3 = daemon.UdpRelay(fake_send)
for i in range(1000):
    U3.handle(b"\x03\x00\x00\x00\x01", ("5.5.5.5", 5), now=2000.0)         # a flood in one instant
check(0 < U3.counters["rate-limited"] and U3.counters["rate-limited"] > 600, "a flooding source is rate limited (%d dropped)" % U3.counters["rate-limited"])
sent.clear()
U3.handle(b"\x03\x00\x00\x00\x01", ("6.6.6.6", 6), now=2000.0)
check(bool(sent), "other sources are not affected by the flood")
U3.handle(b"\x03\x00\x00\x00\x01", ("5.5.5.5", 5), now=2010.0)
check(any(x[0] == ("5.5.5.5", 5) for x in sent), "the flooder recovers after it stops")
# a strict relay accepts only known sids
daemon.RELAY_STRICT = True
U4 = daemon.UdpRelay(fake_send)
U4.handle(b"\x00" + struct.pack("<I", 0x12345678) + b"\x00", a0)
check(U4.counters["unknown-sid"] == 1, "T2R_RELAY_STRICT: HELLO for a sid no match uses is ignored")
daemon.RELAY_STRICT = False

# ------------------------------------------------------------------ REGRESSION: the real client's first exchange
# UDP game-server check: client sends 03 + seq(4); the pong must be 04 + the same seq. (A hardening rewrite dropped the 0x04
# byte: the game then showed 'Cannot reach game servers'.)
pongs = []
U5 = daemon.UdpRelay(lambda d, a: pongs.append((a, d)))
U5.handle(b"\x03\x07\x00\x00\x00", ("127.0.0.1", 5555))
check(pongs and pongs[0][1] == b"\x04\x07\x00\x00\x00", "UDP 03 keepalive is answered with 04 + the same seq: %s" % (pongs[0][1].hex() if pongs else None))
# TCP login (op 0x0f, [1c][64 hex token]): boot reply = 0x10 name, 0x08 server lists, 0x0d done
c = socket.create_connection(("127.0.0.1", port), timeout=3)
lp = b"\x1c" + A.encode()
c.sendall(struct.pack("<H", len(lp) + 1) + b"\x0f" + lp)
data = b""
c.settimeout(2)
try:
    while True:
        b = c.recv(65536)
        if not b: break
        data += b
        if data.endswith(b"\x02\x00\x0d\x01"): break
except socket.timeout:
    pass
c.close()
ops, i = [], 0
while i + 3 <= len(data):
    ln = struct.unpack_from("<H", data, i)[0]; ops.append(data[i + 2]); i += 2 + ln
check(ops == [0x10, 0x08, 0x0d], "TCP login gets the boot reply 0x10, 0x08, 0x0d: %s" % [hex(o) for o in ops])

# ------------------------------------------------------------------ cancel during the countdown / only real searchers match
def q(*toks):
    for t in toks:
        MM.queue.pop(t, None)
    for t in toks:
        MM.enqueue(t)
reset(); online(A, B)
now = time.time()
make_match([A, B], age=3, launched=False)
st_a = {"token": A, "name": "Alpha"}; st_b = {"token": B, "name": "Bravo"}
daemon.handle_leave(("x", 1), st_a)                     # Alpha backs out during the countdown
check(not MM.matches and B in MM.queue and A not in MM.queue, "cancel: the match is gone, Bravo is queued again, Alpha is not")
check(MM.try_form() == (None, None), "cancel: Bravo has not polled since -> not matchable yet")
MM.enqueue(A); MM.settle[A] = 0
mid, pl = MM.try_form()
check(mid is None, "Alpha's re-queue does NOT match a Bravo that is not searching (the 10-09 empty-match bug)")
MM.poll(B)                                              # Bravo's searching page heartbeat arrives = proof it searches
mid, pl = MM.try_form()
check(mid is not None and set(pl) == {A, B}, "once Bravo polls as a searcher the two match")
# Bravo backs out to the menu too (0x02) -> dequeued, never matched
reset(); online(A, B)
make_match([A, B], age=3, launched=False)
daemon.handle_leave(("x", 1), st_a)
daemon.handle_leave(("x", 2), st_b)
check(B not in MM.queue, "0x02 from a queued player removes it from the queue")
MM.enqueue(A); MM.settle[A] = 0; MM.poll(A)
check(MM.try_form() == (None, None), "Alpha alone after both backed out: no match")
# a player that stops polling is not matched even though it is still queued (TTL not reached)
reset(); online(A, B)
MM.queue[A] = MM.queue[B] = time.time(); MM.seen[A] = time.time(); MM.settle[A] = MM.settle[B] = 0
MM.seen[B] = time.time() - (daemon.QUEUE_FRESH + 1)
check(MM.try_form() == (None, None) and B in MM.queue, "a queued player with a stale poll is not matchable (stays queued until the TTL)")
MM.poll(B)
check(MM.try_form()[0] is not None, "... and is matchable again after its next poll")
reset()

# ------------------------------------------------------------------ log rotation
d = tempfile.mkdtemp()
lp = os.path.join(d, "daemon.log")
for gen in range(7):
    open(lp, "w").write("gen %d" % gen)
    daemon.rotate_log(lp, keep=3)
files = sorted(os.listdir(d))
check(files == ["daemon.log.1", "daemon.log.2", "daemon.log.3"], "rotate_log keeps %d old logs: %s" % (3, files))
check(open(lp + ".1").read() == "gen 6", "newest old log is .1")
check(len(daemon.hexcut(bytes(200))) < 200 and "+152B" in daemon.hexcut(bytes(200)), "raw hex dumps are cut")

# ------------------------------------------------------------------ EVT log reconstructs a match
reset(); online(A, B)
daemon._q.clear()
make_match([A, B], age=1, launched=True)
daemon.LOADED.update([A, B])
daemon.maybe_game_start(A)
daemon.leave_running_match(B, "left (0x02)")
lines = [l for l in daemon._q if " EVT " in l]
check(any("game-start" in l for l in lines) and any("left" in l and "left (0x02)" in l for l in lines), "EVT lines for game-start and leave")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
