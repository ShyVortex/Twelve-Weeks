"""Unit tests for the long-uptime state pruning of tools/daemon.py (soak audit): gc_state bounds every registry keyed by player / address / match,
the UDP / presence tables are capped, rate limiters forget quiet addresses, PerfScores / MatchMaker / Parties drop gone players.
Run: python tools/tests/test_daemon_gc.py   (temp DB, no ports)."""
import os, sys, socket, tempfile, time, collections
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "t2r.db")
daemon.LOG_PATH = os.path.join(os.path.dirname(daemon.DB_PATH), "daemon.log")

def tok(n):
    return ("%08x" % n) * 8
OLD1, OLD2, LIVE, QUEUED, RECENT = tok(1), tok(2), tok(3), tok(4), tok(5)
MM = daemon.MM
now = time.time()

def fill():
    """One entry per registry for an old (gone) token, plus the same for the active ones."""
    for t in (OLD1, OLD2, LIVE, QUEUED, RECENT):
        daemon.PRES.touch(t, "x")
        daemon.PRES.players[t]["last"] = now - (7200 if t in (OLD1, OLD2) else 5)
        daemon.FEED_SEEN[t] = {"a"}; daemon.BOOST_PICK[t] = 1; daemon.BOOST_ACTIVE[t] = 1; daemon.CLAN_MATCH[t] = "m-live"
        daemon.PING_LOC[t] = "x"; daemon.LOC_HIST[t] = collections.deque([1]); daemon.LOC_SPIKES[t] = 0; daemon.REGION[t] = "EU"
        daemon.REGION_CAND[t] = ("EU", 1); daemon.JIP_LATE[t] = ("m", now); daemon.JIP_STARTED[t] = ("m", now); daemon.JIP_REPUSH[t] = (now, 1)
        daemon._JIP_WAIT_LOG[t] = now; daemon.LOADED_T[t] = now; daemon._SILENT[t] = now; daemon.LOADED.add(t); daemon.CD_GOT.add(t)
        MM.seen[t] = now; MM.settle[t] = now; MM.departed_t[t] = now; MM.departed_vol.add(t); MM.left[t] = (now, now)
        MM.late_bonus[t] = ("m", 5); MM.late_mult[t] = ("m", 2)
    daemon.NAMELESS_BY_IP["9.9.9.9"] = OLD1; daemon.NAMELESS_BY_IP["8.8.8.8"] = LIVE
    daemon.PING[(OLD1, OLD2)] = [1]; daemon.PING[(LIVE, RECENT)] = [1]
    daemon.VOTES[frozenset([OLD1, OLD2])] = {}; daemon.VOTES[frozenset([LIVE, RECENT])] = {}
    daemon.MATCH_MAP[frozenset([OLD1])] = 1; daemon.SID_KEEP[frozenset([OLD2])] = 5; daemon.TIMING[frozenset([OLD1, OLD2])] = {}
    daemon.CLAN_ENDED["m-old"] = now - 7200; daemon.CLAN_ENDED["m-new"] = now - 10
    daemon.CLAN_QUITTERS.update({(OLD1, "m-gone"), (LIVE, "m-live"), (OLD2, "m-new")})
    daemon.CLAN_EXCUSED.update({(OLD1, "m-gone"), (LIVE, "m-live")})
    daemon.CLAN_LAST_DEPART["m-gone"] = (now - 7200, OLD1); daemon.CLAN_LAST_DEPART["m-live"] = (now, LIVE)
    daemon.ABORT_AWARDED.update({"m-gone", "m-live", "m-new"})
    daemon._JIP_LAST_WHY[OLD1] = "x"; daemon._JIP_LAST_WHY[LIVE] = "x"
    with MM.lock:
        MM.matches["m-live"] = [LIVE, RECENT]
        MM.queue[QUEUED] = now
    daemon.PARTIES.of[OLD1] = "p1"; daemon.PARTIES.of[OLD2] = "p1"; daemon.PARTIES.of[LIVE] = "p2"
    daemon.PARTIES.inv[OLD1] = {OLD2: now - 1000}; daemon.PARTIES.inv[LIVE] = {RECENT: now - 400, QUEUED: now}

fill()
r = daemon.gc_state(now, ttl=3600)
check(r.get("PRES") == 2, "PRES.players: the two tokens silent for 2 h are dropped, the other three stay (%s)" % r)
check(set(daemon.PRES.players) == {LIVE, QUEUED, RECENT}, "PRES keeps live / queued / recent")
for name in ("FEED_SEEN", "BOOST_PICK", "BOOST_ACTIVE", "CLAN_MATCH", "PING_LOC", "LOC_HIST", "LOC_SPIKES", "REGION", "REGION_CAND", "JIP_LATE", "JIP_STARTED",
             "JIP_REPUSH", "_JIP_WAIT_LOG", "LOADED_T", "_SILENT", "LOADED", "CD_GOT"):
    d = getattr(daemon, name)
    check(OLD1 not in d and OLD2 not in d and LIVE in d and QUEUED in d and RECENT in d, "%s: gone tokens dropped, active kept" % name)
check("9.9.9.9" not in daemon.NAMELESS_BY_IP and "8.8.8.8" in daemon.NAMELESS_BY_IP, "NAMELESS_BY_IP: an address whose token is gone is dropped")
check((OLD1, OLD2) not in daemon.PING and (LIVE, RECENT) in daemon.PING, "PING pairs of gone players dropped")
check(frozenset([OLD1, OLD2]) not in daemon.VOTES and frozenset([LIVE, RECENT]) in daemon.VOTES, "VOTES of a match nobody is in any more dropped, live kept")
check(not daemon.MATCH_MAP and not daemon.SID_KEEP and not daemon.TIMING, "MATCH_MAP / SID_KEEP / TIMING of gone players dropped")
check("m-old" not in daemon.CLAN_ENDED and "m-new" in daemon.CLAN_ENDED, "CLAN_ENDED older than an hour dropped")
check((OLD1, "m-gone") not in daemon.CLAN_QUITTERS and (LIVE, "m-live") in daemon.CLAN_QUITTERS and (OLD2, "m-new") in daemon.CLAN_QUITTERS,
      "CLAN_QUITTERS: dead match dropped; a live match and a match whose clan day is still waiting stay")
check((OLD1, "m-gone") not in daemon.CLAN_EXCUSED and (LIVE, "m-live") in daemon.CLAN_EXCUSED, "CLAN_EXCUSED likewise")
check("m-gone" not in daemon.CLAN_LAST_DEPART and "m-live" in daemon.CLAN_LAST_DEPART, "CLAN_LAST_DEPART likewise")
check(daemon.ABORT_AWARDED == {"m-live", "m-new"}, "ABORT_AWARDED: only the dead match went (%s)" % daemon.ABORT_AWARDED)
check(OLD1 not in daemon._JIP_LAST_WHY and LIVE in daemon._JIP_LAST_WHY, "_JIP_LAST_WHY pruned")
for name in ("seen", "settle", "departed_t", "late_bonus", "late_mult", "left"):
    d = getattr(MM, name)
    check(OLD1 not in d and LIVE in d and QUEUED in d, "MatchMaker.%s: gone tokens dropped, queued / in-match kept" % name)
check(OLD1 not in MM.departed_vol and LIVE in MM.departed_vol, "MatchMaker.departed_vol pruned")
check(OLD1 not in daemon.PARTIES.of and OLD2 not in daemon.PARTIES.of and LIVE in daemon.PARTIES.of, "Parties.of: gone members dropped")
check(OLD1 not in daemon.PARTIES.inv and RECENT not in daemon.PARTIES.inv.get(LIVE, {}) and QUEUED in daemon.PARTIES.inv[LIVE], "Parties.inv: expired / gone invitations dropped")
check(MM.matches.get("m-live") == [LIVE, RECENT] and QUEUED in MM.queue, "gc never touches the queue or a live match")
r2 = daemon.gc_state(now, ttl=3600)
check(not r2, "a second pass finds nothing more (%s)" % r2)

# left older than 10 min goes even for an active token
with MM.lock: MM.left[LIVE] = (now - 700, now - 800)
daemon.gc_state(now, ttl=3600)
check(LIVE not in MM.left, "MatchMaker.left older than 10 min dropped")

# gc_tick respects its interval
daemon._gc_last[0] = 0.0
daemon.PRES.touch(OLD1, "x"); daemon.PRES.players[OLD1]["last"] = now - 99999
check(daemon.gc_tick(now) is not None and daemon.gc_tick(now + 1) is None and daemon.gc_tick(now + daemon.STATE_GC_S + 1) is not None, "gc_tick runs at most every STATE_GC_S")

# ------------------------------------------------------------------ presence tables
P = daemon.Presence()
for i in range(P.UDP_SEEN_MAX + 500):
    P.ping(("10.1.%d.%d" % (i // 250, i % 250), 4000 + i % 60000))
check(len(P.udp_seen) <= P.UDP_SEEN_MAX, "Presence.udp_seen capped at %d (%d)" % (P.UDP_SEEN_MAX, len(P.udp_seen)))
P.touch("a", "A"); P.touch("b", "B"); P.players["a"]["last"] = time.time() - 10000
check(P.prune(3600) == 1 and "a" not in P.players and "b" in P.players, "Presence.prune drops by age")
P.touch("c", "C"); P.players["c"]["last"] = time.time() - 10000
check(P.prune(3600, keep={"c"}) == 0 and "c" in P.players, "Presence.prune keeps `keep`")

daemon.PEERS.clear()
for i in range(daemon.PEERS_MAX + 300):
    daemon.peer_seen("10.%d.%d.%d" % (i // 65536, (i // 256) % 256, i % 256), ("x", i))
check(len(daemon.PEERS) <= daemon.PEERS_MAX, "PEERS capped (%d)" % len(daemon.PEERS))
check(list(daemon.PEERS)[-1].endswith(str((daemon.PEERS_MAX + 299) % 256)), "PEERS keeps the newest")

sent = []
U = daemon.UdpRelay(lambda d, a: sent.append(a))
t0 = 5000.0
for i in range(U.TABLE_MAX + 200):
    U.handle(b"\x03\x00\x00\x00\x01", ("7.7.%d.%d" % (i // 250, i % 250), 1000 + i), now=t0 + i * 0.001)
check(len(U.KA) <= U.TABLE_MAX, "keepalive relay table capped at %d (%d): one packet no longer fans out to thousands" % (U.TABLE_MAX, len(U.KA)))
before = len(sent)
U.handle(b"\x03\x00\x00\x00\x01", ("7.8.8.8", 1), now=t0 + 5)
check(len(sent) - before <= U.TABLE_MAX + 2, "one keepalive is sent to at most the table size (%d)" % (len(sent) - before))

U = daemon.UdpRelay(lambda d, a: None)
for i in range(9000):
    U.handle(b"\x03\x00\x00\x00\x01", ("13.%d.%d.%d" % (i // 65536, (i // 256) % 256, i % 256), 7), now=50.0)
check(len(U.seen) <= 4100, "UdpRelay.seen (log throttle memory) stays bounded inside the prune interval (%d)" % len(U.seen))
U = daemon.UdpRelay(lambda d, a: None)
for i in range(4200):
    U.handle(b"\x03\x00\x00\x00\x01", ("11.%d.%d.%d" % (i // 65536, (i // 256) % 256, i % 256), 5), now=100.0)
n_full = len(U.buckets)
U.handle(b"\x03\x00\x00\x00\x01", ("12.0.0.1", 5), now=200.0)       # 100 s later: the quiet ones are forgotten, the newcomer is NOT dropped
check(n_full >= 4096 and ("12.0.0.1", 5) in U.buckets and len(U.buckets) < 100, "an address spray no longer locks out new sources once the old buckets are quiet (%d -> %d)" % (n_full, len(U.buckets)))

# ------------------------------------------------------------------ limiter / perf
L = daemon.AddrLimiter(3, 10.0)
for i in range(50):
    L.allow("ip%d" % i, now=100.0)
check(L.prune(now=105.0) == 0 and len(L.hits) == 50, "AddrLimiter.prune keeps addresses inside their window")
check(L.prune(now=200.0) == 50 and not L.hits, "AddrLimiter.prune drops quiet addresses")

import hostmig
clock = [1000.0]
PS = hostmig.PerfScores(now=lambda: clock[0])
PS.report("t1", {"n1": 0}, steamid=11); PS.report("t2", {"n1": 0})
clock[0] += hostmig.PERF_FRESH_S + 5
PS.report("t3", {"n1": 0}, steamid=33)
check(PS.prune() == 3 and set(PS.by_token) == {"t3"} and set(PS.by_steam) == {33}, "PerfScores.prune drops stale reports (token + steam rows)")

# state_sizes still works and sees everything
sz = daemon.state_sizes()
check("Presence.players" in sz and "MatchMaker.queue" in sz and sz["threads"] >= 1, "state_sizes lists the registries")

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
