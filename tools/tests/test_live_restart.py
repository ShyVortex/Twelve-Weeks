"""Live matches survive a daemon restart (re/premortem-matchmaking.md H3): offline tests, plain python, temp DB, no sockets.
Run: python tools/tests/test_live_restart.py"""
import os, sys, tempfile, time, json, struct
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

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
                  T2R_FILL_WAIT="0", T2R_P2P="0", T2R_HOST_MIGRATION="1", T2R_LIVE_STATE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
daemon.evt = lambda *a, **k: None
MM, HM, GL = daemon.MM, daemon.HM, daemon.GL
HM.collect = 0.3
with daemon._dblock, daemon.db() as c:
    for t in T:
        c.execute("INSERT OR IGNORE INTO players(token,name,matches,wins,draws,last_seen) VALUES(?,?,1,0,0,?)", (t, "x", time.time()))
LIVE = daemon.live_path()

def wipe(file_too=False):
    """What a daemon restart does to memory."""
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed", "departed_t", "clock", "polled", "joining",
              "lives", "late_bonus", "late_mult", "started_t"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.departed_vol.clear(); MM.timed_out.clear(); MM.ended_at.clear()
    HM.matches.clear(); HM.by_token.clear(); GL.held.clear(); GL.want.clear(); daemon.INT.matches.clear(); daemon.INT.by_token.clear()
    for d in (daemon.CLAN_MATCH, daemon.CLAN_ENDED, daemon.CLAN_PENDING, daemon.CLAN_DUE, daemon.MATCH_MAP, daemon.MATCH_P2P, daemon.SID_KEEP,
              daemon.LOADED_T):
        d.clear()
    daemon.RESULT_BOOKED.clear(); daemon.END_BY_REPORTS.clear(); daemon.CLAN_REPORTED_END.clear()      # (the test reuses one match id across restarts)
    daemon.CLAN_QUITTERS.clear(); daemon.CLAN_EXCUSED.clear(); daemon.LOADED.clear(); daemon.READOPT.clear()
    with daemon.PRES.lock: daemon.PRES.players.clear()
    if file_too and os.path.exists(LIVE): os.remove(LIVE)

def start_match(mid, players, map_idx=3):
    """A started match the way maybe_game_start leaves it."""
    now = time.time()
    with MM.lock:
        MM.matches[mid] = list(players); MM.formed[mid] = now - 120; MM.launched.add(mid); MM.started.add(mid); MM.started_t[mid] = now - 100
        MM.qtime[mid] = {}
    daemon.MATCH_MAP[frozenset(players)] = map_idx; daemon.MATCH_P2P[frozenset(players)] = True
    HM.start(mid, players)
    for t in players:
        daemon.CLAN_MATCH[t] = mid; daemon.LOADED.add(t); daemon.PRES.touch(t, "x")

def e3(t, rem=500.0, dur=900.0):
    return bytes.fromhex("") + t.encode("latin1") + bytes([1]) + struct.pack("<ff", rem, dur)

def poll(t, flags=0, epoch=0):
    r = HM.poll(t, flags, epoch)
    return {"enabled": r[0], "host": r[1], "epoch": r[2], "alive": r[3], "state": r[4]}

MID = "a1b2c3d4"
PL = T[:4]

# ------------------------------------------------------------ (1) restart mid-match -> clients poll -> re-adopted -> result booked
wipe(True)
start_match(MID, PL)
for t in PL: poll(t)
GL.claim(MID, 0, T[0], 1, set(PL), pre=False, slot=0)
held_before = GL.export_held(MID)
check(daemon.live_save() and os.path.exists(LIVE) and not os.path.exists(LIVE + ".tmp"), "live state written atomically (no .tmp left)")
saved = json.load(open(LIVE))
check([r["mid"] for r in saved["matches"]] == [MID] and saved["matches"][0]["players"] == PL, "file holds the started match with its player / slot order")

wipe()                                                         # --- daemon restart ---
check(MM.mid_of(T[0]) is None and not HM.has(T[0]), "after the restart nothing is known in memory")
check(HM.poll(T[1], 0, 0)[3] == 0xFF, "old behaviour without the file: unknown match answers 'keep going' (alive mask 0xFF)")
loaded = daemon.live_load()
check(loaded == [MID] and MM.mid_of(T[0]) is None, "record loaded, parked in READOPT (not yet a live match)")
check(daemon.CLAN_MATCH.get(T[2]) == MID, "clan match ids restored at once (a day report finds its match)")
rep = daemon.jip_roster_op(e3(T[1]))                           # a client's clock report = its sign of life
check(rep is not None and MM.mid_of(T[1]) == MID and MM.players_of(T[1]) == PL, "first 0xE3 poll re-adopts the match (players + slots)")
check(MID in MM.started and MID in MM.launched and HM.has(T[0]) and not daemon.READOPT, "started / launched / host record back, READOPT empty")
check(daemon.MATCH_MAP.get(frozenset(PL)) == 3 and daemon.MATCH_P2P.get(frozenset(PL)) is True, "map and net mode restored")
check(daemon.map_index(PL) == 3, "map_index() of the players answers the old map")
check(GL.export_held(MID) == held_before, "gun-limit claims restored")
p = poll(T[2])
check(p["host"] == 0 and p["epoch"] == 0 and p["state"] == 0 and p["alive"] == 0b1111, "host-migration poll after the re-adopt: host slot 0, epoch 0, all alive")
check(MM.clock.get(MID) and MM.clock[MID][0] == 500.0, "the first clock report rebuilt the clock")
for t in PL:
    check(daemon.silence(t, time.time()) < 5, "reaper silence of %s is fresh after the re-adopt" % NAMES[T.index(t)])
reaped = daemon.reap_matches()
check(not [r for r in reaped if r[0] == MID] and MM.mid_of(T[0]) == MID, "the reaper leaves the re-adopted match alone")
# result from the host: wins booked, clan end known
st = {"token": T[0]}
daemon.handle_match_end(("127.0.0.1", 1), st, [(0x12, bytes([0]))])
with daemon._dblock, daemon.db() as c:
    w = {t: tuple(c.execute("SELECT wins, draws FROM players WHERE token=?", (t,)).fetchone()) for t in PL}
check(w[T[0]] == (1, 0) and w[T[2]] == (1, 0) and w[T[1]] == (0, 0) and w[T[3]] == (0, 0), "0x12 after the restart books the win for team 0")
check(MID in daemon.CLAN_ENDED and MID in MM.ended, "clan end + scoreboard hold set (clan credit books normally)")
before = daemon.CLAN_MATCH.get(T[1])
daemon.clan_report(T[1], 0, 2)                                 # the day report finds its match (log used to say 'without a started match')
check(before == MID and T[1] not in daemon.CLAN_PENDING, "clan day report of the match resolved (nothing left pending)")
daemon.MM.drop(MID); HM.end(MID)

# ------------------------------------------------------------ (2) host claims first via the result op / other claim paths
for name, fn in (("0x12 result", None), ("0xE2 clan report", lambda t: daemon.clan_report(t, 0, 0)), ("0xE6 poll via claim", lambda t: daemon.readopt_claim(t)),
                 ("0xBA notice", lambda t: daemon.notice_op(t.encode("latin1") + bytes([1, 0])))):
    wipe(True)
    start_match(MID, PL); daemon.live_save(); wipe(); daemon.live_load()
    if fn is None:
        daemon.handle_match_end(("127.0.0.1", 1), {"token": T[0]}, [(0x12, bytes([1]))])
        with daemon._dblock, daemon.db() as c:
            r = c.execute("SELECT wins FROM players WHERE token=?", (T[1],)).fetchone()
        ok = MID in MM.ended and r[0] >= 1
    else:
        fn(T[3]); ok = MM.mid_of(T[3]) == MID or (MID in MM.matches and MID not in daemon.READOPT)
    check(ok, "claim path works: " + name)
    MM.drop(MID); HM.end(MID)

# ------------------------------------------------------------ (3) restart with no clients returning -> dropped
wipe(True)
start_match(MID, PL); daemon.live_save(); wipe()
daemon.live_load()
check(daemon.readopt_expire(time.time() + 10) == [], "a record is kept while the claim window runs")
check(daemon.readopt_claim("f" * 64) is None and MID in daemon.READOPT, "a stranger's token claims nothing")
check(daemon.readopt_expire(time.time() + daemon.LIVE_CLAIM_S + 1) == [MID] and not daemon.READOPT, "unclaimed record dropped after the claim window")
check(MM.mid_of(T[0]) is None and not MM.matches, "no ghost match left in the matchmaker")
check(daemon.readopt_claim(T[0]) is None, "a late sign of life after the drop claims nothing")
# a second restart inside the window must not lose the record
wipe(True)
start_match(MID, PL); daemon.live_save(); wipe(); daemon.live_load()
daemon.live_save()                                              # 2nd daemon instance writes while the record is still unclaimed
wipe(); check(daemon.live_load() == [MID], "unclaimed record survives a second restart inside its window")
# too old
d = json.load(open(LIVE)); d["saved_at"] = time.time() - daemon.LIVE_MAX_AGE - 5; json.dump(d, open(LIVE, "w"))
wipe(); check(daemon.live_load() == [] and not daemon.READOPT, "a file older than LIVE_MAX_AGE is ignored")
d["saved_at"] = time.time(); d["matches"][0]["saved"] = time.time() - daemon.LIVE_MAX_AGE - 5; json.dump(d, open(LIVE, "w"))
wipe(); check(daemon.live_load() == [], "a record older than LIVE_MAX_AGE is ignored")
open(LIVE, "w").write("{ not json"); wipe(); check(daemon.live_load() == [], "corrupt file ignored")
json.dump({"v": 99, "saved_at": time.time(), "matches": []}, open(LIVE, "w")); wipe(); check(daemon.live_load() == [], "unknown file version ignored")

# ------------------------------------------------------------ (4) restart during a host migration
wipe(True)
start_match(MID, PL)
for t in PL: poll(t)
time.sleep(0.05)
HM.depart(T[0], "crashed")                                     # the host is gone, a successor is being collected
check(HM.host_info(MID)["pending"], "host loss pending before the restart")
daemon.live_save(); wipe()
daemon.live_load()
check(daemon.readopt_claim(T[2]) == MID, "a survivor's poll re-adopts the match mid-migration")
check(HM.host_info(MID)["pending"] and HM.host_info(MID)["host"] == 0, "the pending host loss is still pending (no successor invented)")
check(0 in HM.matches[MID]["gone"], "the dead host stays gone")
for t in PL[1:]:
    poll(t, 1, 0)                                              # survivors ask again, the host is silent for them
time.sleep(HM.collect + 0.1)
HM.tick()
hi = HM.host_info(MID)
check(not hi["pending"] and hi["epoch"] == 1 and hi["host"] in (1, 2, 3), "migration completes after the restart: new host slot %s epoch %s" % (hi["host"], hi["epoch"]))
p = poll(T[1], 0, 0)
check(p["epoch"] == 1 and p["host"] == hi["host"] and not p["alive"] & 1, "polls now hand out the new host and the alive mask without the old host")
# epoch kept across a restart after the migration
daemon.live_save(); wipe(); daemon.live_load(); daemon.readopt_claim(T[3])
check(HM.host_info(MID)["epoch"] == 1 and HM.host_info(MID)["host"] == hi["host"], "epoch / host survive a second restart")
daemon.MM.drop(MID); HM.end(MID)

# ------------------------------------------------------------ (5) players who left / queued again
wipe(True)
start_match(MID, PL)
with MM.lock: MM.departed[MID] = {T[3]}; MM.departed_t[T[3]] = time.time() - 30
HM.depart(T[3], "left")
daemon.live_save(); wipe(); daemon.live_load()
check(daemon.readopt_claim(T[3]) is None and MID in daemon.READOPT, "a player who had left cannot re-attach the match")
MM.queue[T[1]] = time.time(); MM.seen[T[1]] = time.time()      # Bob searched again before anybody reported
check(daemon.readopt_claim(T[0]) == MID, "Alice re-attaches the match")
check(T[1] in MM.departed.get(MID, ()) and T[3] in MM.departed.get(MID, ()) and T[0] not in MM.departed.get(MID, ()),
      "Bob (queued again) and Dave (left) are departed, Alice and Carol play on")
check(MM.mid_of(T[1]) is None and MM.in_match(T[1]) is False, "Bob can still queue")
check({1, 3} <= HM.matches[MID]["gone"], "host migration marks Bob and Dave gone")
daemon.MM.drop(MID); HM.end(MID); MM.queue.clear()

# ------------------------------------------------------------ (6) nothing started / ended = nothing saved; switch off
wipe(True)
with MM.lock: MM.matches[MID] = list(PL); MM.formed[MID] = time.time()       # formed, countdown running: not persisted
check(daemon.live_save() is False and not os.path.exists(LIVE), "no running match, nothing to write")
start_match("ee11ee11", PL); MM.ended.add("ee11ee11")
data = daemon.live_export()
check(data["matches"] == [], "an ended match is not persisted (its result is booked)")
MM.matches.pop(MID, None)
daemon.LIVE_ON = False; wipe(True); start_match(MID, PL)
check(daemon.live_save() is False and not os.path.exists(LIVE) and daemon.live_load() == [], "T2R_LIVE_STATE=0 turns it off")
daemon.LIVE_ON = True

# ------------------------------------------------------------ (7) a join in progress survives a restart (551de4ee: a player joined as slot 4
# 14 s before a restart, the re-adopted match lacked them and every client removed them from its roster)
wipe(True)
start_match(MID, PL[:3])
MM.matches[MID].append(T[4]); MM.joining[T[4]] = (MID, time.time() - 14)           # still loading
daemon.live_save()
saved = json.load(open(LIVE))["matches"][0]
check(T[4] not in saved["departed"] and T[4] in saved["joining"], "a joiner is saved as a joiner, not as departed")
wipe(); daemon.live_load(); daemon.readopt_claim(T[0])
check(T[4] not in MM.departed.get(MID, ()) and MM.players_of(T[0])[3] == T[4], "re-adopted match keeps the joiner in its slot")
check(MM.jip_joiners(MID) == [T[4]] and 13 < MM.jip_age(T[4]) < 20, "the join is resumed (MM.joining, original join time)")
check(T[4] not in daemon.LOADED, "a joiner still loading is not marked loaded")
hp = poll(T[4])
check(hp["alive"] & (1 << 3) and hp["state"] != 2, "host migration counts the joiner as alive")
daemon.LOADED.add(T[4])                                        # it finishes loading (0x07)
check(not daemon.maybe_game_start(T[4]), "GAME-START waits until the others' rosters list the joiner again (jip_acked)")
for t in PL[:3]: daemon.jip_roster_op(e3(t))                   # their clock reports: the 0xE5 reply carries the server roster with the joiner
check(daemon.maybe_game_start(T[4]), "the loaded joiner gets its GAME-START after the restart")
check(T[4] in daemon.JIP_STARTED and not MM.jip_joiners(MID), "join finished: no longer joining")
daemon.MM.drop(MID); HM.end(MID)
# joiner that had already loaded before the restart: started right at the re-adopt
wipe(True)
start_match(MID, PL[:3])
MM.matches[MID].append(T[4]); MM.joining[T[4]] = (MID, time.time() - 10); daemon.LOADED.add(T[4])
daemon.live_save(); wipe(); daemon.live_load(); daemon.readopt_claim(T[1])
check(T[4] in daemon.LOADED and MM.jip_joiners(MID) == [T[4]], "a joiner loaded before the restart is re-adopted as loaded, still joining")
for t in PL[:3]: daemon.jip_roster_op(e3(t))
daemon.reap_matches()                                          # the reaper's join-in-progress pass starts a loaded joiner
check(T[4] in daemon.JIP_STARTED and not MM.jip_joiners(MID), "... and the reaper starts it once the rosters list it")
daemon.MM.drop(MID); HM.end(MID)
# old file format (no 'joining' key, joiner listed as departed): unchanged
wipe(True)
start_match(MID, PL[:3])
MM.matches[MID].append(T[4]); MM.departed[MID] = {T[4]}
daemon.live_save(); wipe(); daemon.live_load(); daemon.readopt_claim(T[0])
check(T[4] in MM.departed.get(MID, ()) and not MM.jip_joiners(MID), "a departed slot stays departed")

# fuzz seed 86: a host-migration record whose match is gone (a leave raced the GAME-START bookkeeping) is reaped
wipe()
HM.start("orphan1", [T[0], T[1]])
check("orphan1" in HM.mids(), "(setup) an HM record without a match")
done = daemon.reap_matches()
check("orphan1" not in HM.mids(), "the reaper ends a host-migration record that has no match")

# fuzz seed 98: one match = one clan day per player, even when it left early (day booked), came back through JIP and reported again
wipe()
daemon.clan_side(T[3], 1)
d0 = daemon.clan_state(T[3])["day"]
for mid in ("ma1", "mb2", "ma1"):                      # A, then another match B, then A again (last_mid alone only guards the consecutive repeat)
    daemon.CLAN_MATCH[T[3]] = mid; daemon.CLAN_ENDED[mid] = time.time()
    daemon.clan_report(T[3], 300, 2)
check(daemon.clan_state(T[3])["day"] - d0 == 2, "a match already credited to a player is not credited again later (A, B, A = 2 days, got %d)" % (daemon.clan_state(T[3])["day"] - d0))

# fuzz seed 225: concurrent live_save() calls (status loop + GAME-START threads) must all succeed (they shared one .tmp: PermissionError on Windows)
wipe()
start_match(MID, PL[:3])
import threading as _th
res = []
def _hammer():
    for _ in range(60): res.append(daemon.live_save())
ths = [_th.Thread(target=_hammer) for _ in range(6)]
[t.start() for t in ths]; [t.join() for t in ths]
check(res and all(res), "360 concurrent live_save calls from 6 threads all succeed (%d failed)" % res.count(False))

# Live: a daemon restart closed the session sockets, the clients left the match and reported flags 0 -> six left-early clan days.
# A restored match: its players are session-lost (re-attach recognised) and a flags-0 report right after the re-adoption is excused (no penalty).
wipe(True)
daemon.RESTORED_T.clear(); daemon.SESS_LOST.clear(); daemon.CLAN_DONE.clear(); daemon.CLAN_CREDITED.clear()
start_match("rs1", PL)
for t in PL: poll(t)
daemon.live_save()
wipe()
daemon.live_load() if hasattr(daemon, "live_load") else None
daemon.readopt_claim(PL[0])
check(MM.mid_of(PL[1]) == "rs1" and "rs1" in daemon.RESTORED_T, "(setup) the restored match is back and marked as restored")
check(all(daemon.SESS_LOST.get(t, (0, None))[1] == "rs1" for t in PL), "every restored player counts as a lost session socket (re-attach recognised)")
daemon.clan_side(PL[1], 1)
d0 = daemon.clan_state(PL[1])["day"]
daemon.CLAN_MATCH[PL[1]] = "rs1"
daemon.clan_report(PL[1], 400, 0)                      # the client left the match when the daemon restarted: flags 0, no match end seen
daemon.clan_finalize(PL[1])
check(("%s" % PL[1], "rs1") in daemon.CLAN_EXCUSED, "a flags-0 report right after the restart re-adoption is excused")
st = daemon.clan_state(PL[1])
check(st.get("day", 0) - d0 == 1, "the restart-excused report books a normal day (parts count), not a left-early day")
# a report long after the re-adoption is a real leave again
daemon.RESTORED_T["rs1"] = time.time() - 3600
daemon.clan_side(PL[2], 1)
daemon.CLAN_MATCH[PL[2]] = "rs1"
daemon.CLAN_LAST_DEPART.clear()                       # (PL[1]'s report just departed it: not "after another player left")
daemon.clan_report(PL[2], 400, 0); daemon.clan_finalize(PL[2])
check((PL[2], "rs1") not in daemon.CLAN_EXCUSED, "a report long after the restart is still a normal leave")

# the shutdown resets (RST) the session sockets of players in running matches only
class FakeConn:
    def __init__(s): s.opts = []; s.closed = False
    def setsockopt(s, *a): s.opts.append(a)
    def close(s): s.closed = True
wipe()
start_match("rs2", PL[:2])
cin, cout = FakeConn(), FakeConn()
daemon.SESSIONS.register(PL[0], cin); daemon.SESSIONS.register(T[5], cout)
n = daemon.reset_running_sessions()
check(n == 1 and cin.closed and cin.opts and cin.opts[0][1] == daemon.socket.SO_LINGER and not cout.closed, "shutdown RSTs only the session sockets of players in a running match")
daemon.SESSIONS.unregister(PL[0]); daemon.SESSIONS.unregister(T[5])

wipe(True)
# --- roster_public (launcher "who is online" panel): names + states only
wipe()
start_match("rost1", [T[0], T[1]])
daemon.PRES.touch(T[2], "x"); daemon.PRES.touch(T[3], "x")
with MM.lock: MM.queue[T[3]] = time.time()
daemon.PARTIES.pid = lambda t: "p1" if t == T[2] else None
daemon.PARTIES.members = lambda t: [T[2], T[4]]
ros = daemon.roster_public(daemon.live_snapshot())
by = {r["name"]: r for r in ros}
check(by["Alice"]["state"] == "match" and by["Alice"]["map"] == daemon.MAPS[3][0], "roster: player in a match shows the map name")
check(by["Carol"]["state"] == "party" and by["Carol"]["party"] and by["Carol"]["map"] is None, "roster: party member in menus = party")
check(by["Dave"]["state"] == "searching", "roster: queued player = searching")
check(all(set(r) == {"name", "state", "map", "party"} for r in ros), "roster: name + state fields only (no tokens / ids)")
check(daemon.roster_public({}) == [], "roster: empty snapshot -> []")
print("%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
