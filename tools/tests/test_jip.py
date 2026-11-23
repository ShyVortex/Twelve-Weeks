"""Offline tests for join in progress (daemon T2R_JIP=1): slot / team choice, session id kept, per-match dictionaries re-keyed,
refusals (full, near the end, no fresh clock, host migrated), slot reuse after a leaver, the 0xE3 roster reply, GAME-START of a
joiner only to the joiner.
Run: python tools/tests/test_jip.py   (no sockets are opened, temp DB)."""
import os, sys, tempfile, time, struct
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina", "Hal", "Ivy"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
MM = daemon.MM
for t in T: daemon.PRES.touch(t, "x")

def running(players, mid="m1", left=400.0, map_idx=None):
    """A launched + started match whose clock was just reported."""
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "late_bonus"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear()
    daemon.MATCH_MAP.clear(); daemon.MATCH_P2P.clear(); daemon.SID_KEEP.clear()
    MM.matches[mid] = list(players)
    MM.launched.add(mid); MM.started.add(mid)
    pool = daemon.map_pool(players)
    daemon.MATCH_MAP[frozenset(players)] = pool[0] if map_idx is None else map_idx
    daemon.MATCH_P2P[frozenset(players)] = False
    MM.clock[mid] = (left, 600.0, False, time.time())
    return mid

def search(t):
    now = time.time()
    MM.queue[t] = now; MM.seen[t] = now; MM.settle[t] = 0

# ---- a 3-player match: slots 0,1,2 -> teams 0,1,0. The joiner goes to team 1 = a new odd index 3
mid = running(T[:3])
sid0 = daemon.match_sid(T[:3])
search(T[3])
why = []
r = MM.jip_join(T[3], why)
check(r is not None, "joiner is put into the 3-player match (%s)" % why)
check(r and r[1] == 3 and daemon.team_of(r[1]) == 1, "joiner gets slot 3 = the smaller team (1)")
check(MM.matches[mid] == T[:4], "player list grew in place")
check(daemon.match_sid(MM.matches[mid]) == sid0, "session id is the one the running players hold")
check(frozenset(T[:4]) in daemon.MATCH_MAP and frozenset(T[:3]) not in daemon.MATCH_MAP, "map moved to the new player-set key")
check(T[3] not in MM.queue and MM.joining.get(T[3], (None,))[0] == mid, "joiner left the queue, is 'joining'")
check(MM.mid_of(T[3]) == mid, "match lookup finds the joiner")
check(not MM.jip_acked(T[3]), "others did not poll yet: GAME-START waits")
for t in T[:3]: MM.jip_clock(t, 390.0, 600.0, False)
check(MM.jip_acked(T[3]), "after everyone's poll the joiner may start")
check(MM.jip_done(T[3]) is not None and not MM.jip_joiners(mid), "jip_done clears 'joining'")

# ---- 2v2 -> even: any team, next index 4; fills to 8 then refuses
for i in range(4, 8):
    search(T[i]); r = MM.jip_join(T[i])
    check(r is not None and r[1] == i, "joiner %d gets slot %d" % (i - 3, i))
    MM.jip_done(T[i])
check(len([1 for t in MM.matches[mid]]) == 8, "8 players in the match")
search(T[8]); why = []
check(MM.jip_join(T[8], why) is None, "full match refused")

# ---- refusals
mid = running(T[:3], left=40.0); search(T[3]); why = []
check(MM.jip_join(T[3], why) is None and "40 s left" in " ".join(why), "near the end refused (%s)" % why)
mid = running(T[:3]); MM.clock[mid] = (400.0, 600.0, False, time.time() - 60); search(T[3]); why = []
check(MM.jip_join(T[3], why) is None and "no fresh clock" in " ".join(why), "stale clock report refused")
mid = running(T[:3]); MM.clock[mid] = (400.0, 600.0, True, time.time()); search(T[3])
check(MM.jip_join(T[3]) is None, "ended match refused")
mid = running(T[:3]); MM.ended.add(mid); search(T[3])
check(MM.jip_join(T[3]) is None, "match with its result in refused")
mid = running(T[:3]); MM.started.discard(mid); search(T[3])
check(MM.jip_join(T[3]) is None, "match still loading (no GAME-START) refused")
mid = running(T[:3]); MM.departed[mid] = {T[0]}; search(T[3])
check(MM.jip_join(T[3]) is None, "match whose host left refused")

# ---- slot reuse: 4 players, slot 1 left long ago -> teams 0:{0,2} v 1:{3}: odd slot, reuse 1 (old token replaced)
mid = running(T[:4])
MM.departed[mid] = {T[1]}; MM.departed_t[T[1]] = time.time() - 60
search(T[4]); r = MM.jip_join(T[4])
check(r is not None and r[1] == 1 and MM.matches[mid][1] == T[4], "a leaver's slot on the smaller team is reused")
check(T[1] not in MM.departed.get(mid, ()), "old occupant no longer listed as departed")
# a slot that was freed just now is not handed out yet
mid = running(T[:4])
MM.departed[mid] = {T[1]}; MM.departed_t[T[1]] = time.time()
search(T[4]); r = MM.jip_join(T[4])
check(r is None, "a fresh leaver's slot is kept for JIP_REUSE_S; the only other index is the wrong team: refused")

# ---- a player who crashed out of this match comes back into its own slot (same team), not before JIP_REUSE_S, never the host
mid = running(T[:3]); MM.departed[mid] = {T[2]}; MM.departed_t[T[2]] = time.time() - 60; search(T[2])
r = MM.jip_join(T[2])
check(r is not None and r[0] == mid and r[1] == 2 and MM.matches[mid] == T[:3], "a leaver is put back into its own slot")
check(T[2] not in MM.departed.get(mid, ()), "the returning leaver is no longer listed as departed")
mid = running(T[:3]); MM.departed[mid] = {T[2]}; MM.departed_t[T[2]] = time.time(); search(T[2])
check(MM.jip_join(T[2]) is None, "a leaver is not put back before JIP_REUSE_S")
mid = running(T[:3]); MM.departed[mid] = {T[2]}; MM.departed_t[T[2]] = time.time() - 60; MM.departed_vol.add(T[2]); search(T[2])
r = MM.jip_join(T[2])
check(r is not None and r[0] == mid and r[1] == 2, "a clean leave (op 0x02 - also a freeze dropped to the menu, PT54) still goes back into its own slot when it queues again")
MM.departed_vol.discard(T[2])

# ---- fuzz seed 2: a leaver must not squeeze back into a match that is already full without it (7 active v MATCH_SIZE 6)
_ms = daemon.MATCH_SIZE; daemon.MATCH_SIZE = 6
mid = running(T[:7])
MM.departed[mid] = {T[2]}; MM.departed_t[T[2]] = time.time() - 60       # 6 active of 6, the leaver's old slot still listed
search(T[2]); why = []
check(MM.jip_join(T[2], why) is None, "a leaver does not rejoin a match that is full without it (%s)" % why)
MM.departed[mid] = {T[2], T[3]}; MM.departed_t[T[3]] = time.time() - 60  # one more place free: now it fits
search(T[2]); r = MM.jip_join(T[2])
check(r is not None and r[1] % 2 == 1, "...but does when a place is free (the smaller team 1 since 10-21: its old team 0 has 3 v 2)")
daemon.MATCH_SIZE = _ms

# ---- host migration: join after it, old host rejoin (slot 0 = host role, so the old host gets a free client slot)
import hostmig
def migrated(players, host=2, gone=(0,), mid="m1"):
    mid = running(players, mid)
    hm = hostmig.HostMigration(True, log=lambda *a: None)
    hm.start(mid, players)
    m = hm.matches[mid]; m["host"] = host; m["epoch"] = 1; m["gone"] = set(gone)
    daemon.HM = hm
    MM.departed[mid] = {players[g] for g in gone}
    for g in gone: MM.departed_t[players[g]] = time.time() - 60
    return mid, hm
mid, hm = migrated(T[:4])                       # slots 0..3, host crashed (0), slot 2 hosts now
search(T[4]); why = []; r = MM.jip_join(T[4], why)
check(r is not None and r[1] != 0 and MM.matches[mid][0] == T[0], "join after a host migration works (%s)" % why)
check(r and r[1] == 4 or (r and r[1] in (1, 3)), "joiner gets a free client slot, never slot 0 (got %s)" % (r and r[1]))
mid, hm = migrated(T[:4])
hm.matches[mid]["pending"] = True; search(T[4]); why = []
check(MM.jip_join(T[4], why) is None and "migration in progress" in " ".join(why), "migration still pending: refused")
mid, hm = migrated(T[:4])
hm.matches[mid]["host"] = 0; hm.matches[mid]["epoch"] = 0   # host crashed, migration not decided yet
search(T[4]); why = []
check(MM.jip_join(T[4], why) is None and "host gone" in " ".join(why), "host crashed, no migration yet: refused")
mid, hm = migrated(T[:4]); hm.matches[mid]["given_up"] = True; search(T[4])
check(MM.jip_join(T[4]) is None, "migration given up: refused")
# old host back
mid, hm = migrated(T[:4]); search(T[0]); why = []
r = MM.jip_join(T[0], why)
check(r is not None and r[1] != 0 and r[1] == r[2].index(T[0]) and r[2].count(T[0]) == 1, "old host rejoins in a free client slot, listed once (%s)" % (r and r[1]))
if r:
    pl = MM.matches[mid]
    check(pl[0] == hostmig.placeholder(0) and hostmig.placeholder(0) in MM.departed[mid] and T[0] not in MM.departed[mid], "slot 0 is a departed placeholder")
    check(MM.mid_of(T[0]) == mid and MM.active_of(T[0])[0] == mid, "old host is an active player of the match again")
    check(daemon.team_of(r[1]) == r[1] % 2, "team follows the new slot")
    fr = daemon.match_start_frame(T[0], r[2])
    check(fr[2] == 0x04 and fr[3 + 0x17] == r[1], "its 0x04 record carries the new local slot")
    hm.add_player(mid, T[0], r[1])
    mm = hm.matches[mid]
    check(mm["players"][0] == hostmig.placeholder(0) and mm["players"][r[1]] == T[0] and 0 in mm["gone"] and r[1] not in mm["gone"], "HostMigration: old host index -> placeholder, new slot alive")
    rep = hm.poll(T[0], 0, 0)
    check(rep[1] == 2 and rep[2] == 1 and rep[3] >> r[1] & 1 and not rep[3] & 1, "its first poll learns host slot 2, epoch 1, itself alive, slot 0 gone")
# too soon after the crash
mid, hm = migrated(T[:4]); MM.departed_t[T[0]] = time.time(); search(T[0]); why = []
check(MM.jip_join(T[0], why) is None, "old host not back before JIP_REUSE_S")
# a non-host crashed player after a migration returns into its own slot
mid, hm = migrated(T[:4], gone=(0, 3)); search(T[3])
r = MM.jip_join(T[3])
check(r is not None and r[1] == 3, "a crashed client returns to its own slot after a migration")
daemon.HM = hostmig.HostMigration(daemon.HM.enabled, log=lambda *a: None)

# ---- the 0xE3 roster reply
mid = running(T[:3])
pl = T[1].encode() + bytes([1]) + struct.pack("<ff", 321.0, 600.0)
rep = daemon.jip_roster_op(pl)
ln = struct.unpack_from("<H", rep)[0]
check(rep[2] == 0xE5 and rep[3] == 1 and rep[4] == 3 and ln == len(rep) - 2, "0xE5 reply: enabled, 3 entries")
e = rep[5:5 + 0x32]
check(e[0] == 0 and e[1:6] == b"Alice" and e[0x31] == 0, "entry 0 = slot 0, name, team 0")
check(rep[5 + 0x32 * 1 + 0x31] == 1, "entry 1 is team 1")
check(abs(MM.clock[mid][0] - 321.0) < 0.01, "clock report stored")
check(len(rep) == 5 + 3 * 0x32 + 1 and rep[-1] == 0x81, "reply = header + roster entries + ONE trailing byte (0x80 | wave respawn on; fits an older ext 8-player buffer)")
daemon.WAVE_RESPAWN = False
check(daemon.jip_roster_op(pl)[-1] == 0x80, "T2R_WAVE_RESPAWN=0: trailing byte 0x80 (wave off)")
daemon.WAVE_RESPAWN = True
# late-joiner query (ext flag 0x04): bit 1 of the trailing byte only for a player stamped by jip_start in its CURRENT match
plq = T[1].encode() + bytes([4]) + struct.pack("<ff", 0.0, 0.0)
check(daemon.jip_roster_op(plq)[-1] == 0x81, "flag 0x04, not a joiner: no late bit")
daemon.JIP_LATE[T[1]] = (mid, time.time())
check(daemon.jip_roster_op(plq)[-1] == 0x83, "flag 0x04, joiner of this match: late bit 1")
check(daemon.jip_roster_op(pl)[-1] == 0x81, "a plain clock poll never carries the late bit")
daemon.JIP_LATE[T[1]] = (str(mid) + "-other", time.time())
check(daemon.jip_roster_op(plq)[-1] == 0x81 and T[1] not in daemon.JIP_LATE, "stamp of another match id: not late, dropped")
daemon.JIP = False
check(daemon.jip_roster_op(pl)[3:] == bytes([0, 0, 0x81]), "switch off: enabled 0, no entries (+ the wave byte)")
daemon.BRIDGES.unregister(T[2])
daemon.JIP = True

# =====================================================================================================================================
# matchmaking pass: prefer a running match to a small new one, joiners do not wait for each other, parties together,
# late-join bonus, stuck-joiner re-push, quiet log
# =====================================================================================================================================
import hostmig as _hm
daemon.HM = _hm.HostMigration(True, log=lambda *a: None)
started = []
_real_jip_start = daemon.jip_start
daemon.jip_start = lambda tkn, mid_, slot_, pl_: started.append((tkn, mid_, slot_))
def cnt_teams(mid_):
    dep = MM.departed.get(mid_, ())
    c = [0, 0]
    for i, t in enumerate(MM.matches[mid_]):
        if t not in dep: c[i % 2] += 1
    return c

# ---- try_form: players a running match (>= JIP_PREFER_LEFT s left, room) can take do not form a small new match
mid = running(T[:3], left=400); search(T[3]); search(T[4])
check(MM.try_form() == (None, None) and T[3] in MM.queue and T[4] in MM.queue, "2 searchers + a running match with 400 s and room: no small new match")
started.clear(); daemon.jip_pass()
check([s[0] for s in started] == [T[3], T[4]] and sorted(cnt_teams(mid)) == [2, 3], "jip_pass puts both into the running match, teams %s" % cnt_teams(mid))
mid = running(T[:3], left=120); search(T[3]); search(T[4])
r = MM.try_form()
check(r[0] is None, "running match has 120 s left (< JIP_PREFER_LEFT): the searchers queue for it (no second small match)")
mid = running(T[:1], left=400)
for t in T[1:9]: search(t)
r = MM.try_form()
check(r[0] is not None and len(r[1]) == 8, "8 searchers make a full match even though a running one has room")
mid = running(T[:3], left=400)
for t in T[3:8]: search(t)
check(MM.try_form() == (None, None), "5 searchers: all can fill the running match to 8, no new match")
started.clear(); daemon.jip_pass()
check(len(started) == 5 and len(MM.matches[mid]) == 8 and cnt_teams(mid) == [4, 4], "all five joined: 4 v 4 (%s)" % cnt_teams(mid))
mid = running(T[:2], left=400); MM.clock[mid] = (400.0, 600.0, False, time.time() - 60); search(T[2]); search(T[3])
r = MM.try_form()
check(r[0] is not None, "running match without a fresh clock: not preferred, new match forms")

# ---- the oldest searcher is not kept waiting for a fuller lobby for ever (arrivals reset the quiet timer)
for a in ("queue", "seen", "matches", "settle", "formed", "qtime"):
    getattr(MM, a).clear()
daemon.FILL_WAIT = 15.0
MM.last_arrival = time.time()
for t in T[:3]: search(t)
check(MM.try_form() == (None, None), "3 searchers, a new arrival just now: waits for a fuller lobby")
MM.queue[T[0]] = time.time() - 200
r = MM.try_form()
check(r[0] is not None and len(r[1]) == 3, "the oldest has waited past MAX_WAIT: forms with everybody searching")
daemon.FILL_WAIT = 0.0

# ---- two joiners at once: balanced teams, and the first one's GAME-START does not wait for the other one
mid = running(T[:3])
search(T[3]); search(T[4])
r1 = MM.jip_join(T[3]); r2 = MM.jip_join(T[4])
check(r1[1] == 3 and r2[1] == 4 and cnt_teams(mid) == [3, 2], "two simultaneous joiners: slot 3 (team 1) then slot 4 (team 0), teams 3 v 2")
for t in T[:3]: MM.jip_clock(t, 390.0, 600.0, False)
check(MM.jip_acked(T[3]) and MM.jip_acked(T[4]), "both start after the ESTABLISHED players polled (the other joiner cannot poll yet)")
mid = running(T[:3])
MM.polled[mid] = {T[1]: time.time() - 60}                 # player 1 stopped polling a minute ago (loading / old ext)
search(T[3]); MM.jip_join(T[3])
MM.jip_clock(T[0], 390.0, 600.0, False); MM.jip_clock(T[2], 390.0, 600.0, False)
check(MM.jip_acked(T[3]), "a player that stopped polling long before the join is not waited for")
mid = running(T[:3])
search(T[3]); MM.jip_join(T[3]); MM.jip_clock(T[0], 390.0, 600.0, False)
check(not MM.jip_acked(T[3]), "an established player that has not polled yet is still waited for")

# ---- parties join together
daemon.PARTIES.of.clear()
P1, P2 = T[3], T[4]
daemon.PARTIES.of[P1] = daemon.PARTIES.of[P2] = "pp"
mid = running(T[:3])                                          # teams 0:{0,2} 1:{1}
search(P1); search(P2)
started.clear(); daemon.jip_pass()
pl = MM.matches[mid]
check([s[0] for s in started] == [P1, P2], "party: both members join in one pass")
check(pl.index(P1) % 2 == pl.index(P2) % 2, "party: same team (slots %d and %d)" % (pl.index(P1), pl.index(P2)))
check(pl.index(P1) == 3 and pl.index(P2) == 5 and pl[4] == hostmig.placeholder(4) and pl[4] in MM.departed[mid], "party on team 1: the skipped team-0 index 4 is a gone placeholder")
search(T[5]); r = MM.jip_join(T[5])
check(r is not None and r[1] == 4 and MM.matches[mid][4] == T[5], "the next solo joiner (team 0 is smaller) fills the hole")
check(cnt_teams(mid) == [3, 3], "teams 3 v 3 after the hole is filled (%s)" % cnt_teams(mid))
# a party mate whose friend already plays goes to the friend's team
daemon.PARTIES.of.clear(); daemon.PARTIES.of[T[1]] = daemon.PARTIES.of[T[4]] = "pq"
mid = running(T[:4])                                          # 2 v 2; T[1] is on team 1
search(T[4]); r = MM.jip_join(T[4])
check(r is not None and r[1] % 2 == 1, "joiner goes to its friend's team (slot %s)" % (r and r[1]))
# a party of 2 needs room for both
daemon.PARTIES.of.clear(); daemon.PARTIES.of[T[7]] = daemon.PARTIES.of[T[8]] = "pr"
mid = running(T[:7]); search(T[7]); search(T[8]); why = []
check(MM.jip_join(T[7], why, need=2) is None, "a party of 2 does not fit a match with one free slot")
check(MM.jip_join(T[7]) is not None, "...but a single member would")
# party members always see the match as joinable together for try_form
daemon.PARTIES.of.clear(); daemon.PARTIES.of[T[3]] = daemon.PARTIES.of[T[4]] = "ps"
mid = running(T[:3], left=400); search(T[3]); search(T[4])
check(MM.try_form() == (None, None), "searching party + a running match with room: no new small match")
daemon.PARTIES.of.clear()

# ---- a party that joins a running match lands on ONE team (the follower never takes the balance team)
def party_join(members, base, gone=()):
    daemon.PARTIES.of.clear()
    for m in members: daemon.PARTIES.of[m] = "pz"
    mid_ = running(base)
    for g in gone:
        MM.departed.setdefault(mid_, set()).add(g); MM.departed_t[g] = time.time() - 600
    for m in members: search(m)
    started.clear(); daemon.jip_pass()
    pl_ = MM.matches[mid_]
    return mid_, [pl_.index(m) % 2 for m in members if m in pl_], [s_[0] for s_ in started]
mid, tms, st = party_join([T[5], T[6], T[7]], T[:5])
check(len(st) == 0 or (len(st) == 3 and len(set(tms)) == 1), "party of 3 + 5-player match: one team or not at all (%s %s)" % (tms, len(st)))
mid, tms, st = party_join([T[5], T[6], T[7]], T[:3])
check(len(st) == 3 and len(set(tms)) == 1, "party of 3 + 3-player match: all on one team (%s)" % tms)
mid, tms, st = party_join([T[5], T[6]], T[:5])
check(len(st) == 2 and len(set(tms)) == 1, "party of 2 + 5-player match: same team (%s)" % tms)
mid, tms, st = party_join([T[5], T[6]], T[:5], gone=(T[1], T[3]))      # 3 v 0 active: imbalance rule must not split the pair
check(len(st) == 2 and len(set(tms)) == 1, "party of 2 + 3 v 0 match: same team (%s)" % tms)
#: one member (T[2], slot 2 = team 0) left this very match earlier and comes back WITH a friend: the returning member's old slot
# must not split the pair (it used to go "back" to team 1 while the friend took team 0)
mid_ = running(T[:5]); daemon.PARTIES.of.clear()
MM.departed.setdefault(mid_, set()).add(T[2]); MM.departed_t[T[2]] = time.time() - 600
for m in (T[7], T[2]): daemon.PARTIES.of[m] = "pz"; search(m)
started.clear(); daemon.jip_pass()
tms = [MM.matches[mid_].index(m) % 2 for m in (T[2], T[7]) if m in MM.matches[mid_]]
check(len(started) == 2 and len(set(tms)) == 1, "returning member + friend: same team (%s)" % tms)
mid, tms, st = party_join([T[5]], T[:5])
check(len(st) == 1, "solo joins a 5-player match")
daemon.PARTIES.of.clear()

# ---- late-join bonus (PS4 v1.11 ss-comp-tdm-mode: 100 x (round(minutes elapsed - 1) + 2 / 4 / 6 when the enemy has 1 / 2 / 3 more players))
mid = running(T[:3])                                          # 2 v 1, joiner takes the 1-player team 1
MM.jip_lives(T[0], 0, 5, 8)                                   # team 0 has 5, team 1 has 8
search(T[3]); r = MM.jip_join(T[3])
check(MM.late_bonus.get(T[3]) == (mid, 400), "200 s elapsed (2 points) + outnumbered by one (2 points): 400 (%s)" % (MM.late_bonus.get(T[3]),))
mid = running(T[:4]); MM.jip_lives(T[0], 0, 5, 8)             # 2 v 2, the joiner takes team 0 (even: the next index 4), which is 3 reinforcements down
search(T[4]); r = MM.jip_join(T[4])
check(r[1] == 4 and MM.late_bonus.get(T[4]) == (mid, 200), "even teams, 200 s elapsed: 200 parts (%s)" % (MM.late_bonus.get(T[4]),))
check(MM.late_bonus_take(T[4], "other") == 0 and MM.late_bonus_take(T[4], mid) == 200 and MM.late_bonus_take(T[4], mid) == 0, "paid once, only for that match")
mid = running(T[:4], left=590.0); search(T[4]); MM.jip_join(T[4])
check(T[4] not in MM.late_bonus, "even teams, 10 s elapsed (round(-0.83) = -1): no bonus")
mid = running(T[:4]); MM.departed[mid] = {T[3]}; MM.departed_t[T[3]] = time.time() - 60; MM.jip_lives(T[0], 0, 2, 9); search(T[3]); MM.jip_join(T[3])
check(T[3] not in MM.late_bonus, "a player back in its own slot is no late joiner")
mid = running(T[:3])
rep = daemon.jip_roster_op(T[1].encode() + bytes([1]) + struct.pack("<ff", 321.0, 600.0) + bytes([1, 5, 8]))
check(MM.lives[mid][:2] == (8, 5), "0xE3 lives: reporter on team 1 has 5, enemy 8 -> team 0: 8, team 1: 5 (%s)" % (MM.lives[mid],))
rep2 = daemon.jip_roster_op(T[1].encode() + bytes([1]) + struct.pack("<ff", 321.0, 600.0) + bytes([0xFF, 0xFF, 0xFF]))
check(rep2[2] == 0xE5 and MM.lives[mid][:2] == (8, 5), "unknown lives (0xFF): ignored")

# ---- a joiner that cannot reach the host: the peer table is pushed again (rate limited, bounded)
pushed = []
_real_push = daemon.jip_push_peers
daemon.jip_push_peers = lambda m_, pl_: pushed.append(m_)
mid = running(T[:3]); t0 = time.time()
daemon.JIP_STARTED.clear(); daemon.JIP_REPUSH.clear()
check(not daemon.jip_unreachable(T[1], t0), "not a joiner: nothing to re-push")
daemon.JIP_STARTED[T[1]] = (mid, t0 - 30)
check(daemon.jip_unreachable(T[1], t0) and pushed == [mid], "joiner reports the host silent: peer table re-pushed")
check(not daemon.jip_unreachable(T[1], t0 + 5), "...not again within JIP_REPUSH_S")
check(daemon.jip_unreachable(T[1], t0 + 20), "...again after JIP_REPUSH_S")
n = 2
for k in range(20):
    n += daemon.jip_unreachable(T[1], t0 + 40 + 20 * k)
check(n == daemon.JIP_REPUSH_MAX, "bounded to JIP_REPUSH_MAX (%d) pushes" % n)
daemon.JIP_STARTED[T[2]] = (mid, t0 - 400)
check(not daemon.jip_unreachable(T[2], t0), "an old join (> 5 min): never")
daemon.jip_push_peers = _real_push

# ---- host migration record: a hole below a joiner is gone
hm2 = _hm.HostMigration(True, log=lambda *a: None)
hm2.start("hh", T[:3]); hm2.add_player("hh", T[5], 5)
mm2 = hm2.matches["hh"]
check(len(mm2["players"]) == 6 and mm2["players"][5] == T[5] and {3, 4} <= mm2["gone"] and 5 not in mm2["gone"] and mm2["players"][3] == _hm.placeholder(3),
      "HostMigration.add_player: a hole below the new slot = gone placeholders")

# ---- the 'no running match' reason is logged once, not every second as the seconds left tick down
lines = []
_real_log = daemon.log
daemon.log = lambda *a: lines.append(" ".join(str(x) for x in a))
daemon._JIP_LAST_WHY.clear()
mid = running(T[:3], left=80.0); search(T[3])
for k in range(4):
    MM.clock[mid] = (80.0 - k, 600.0, False, time.time())
    daemon.jip_pass()
daemon.log = _real_log
check(len([l for l in lines if "no running match to join" in l]) == 1, "reason logged once while only the seconds change (%d lines)" % len([l for l in lines if "no running match" in l]))

# ---- the bonus is added to the joiner's parts when its clan day resolves
mid = running(T[:4]); MM.jip_lives(T[0], 0, 5, 8); search(T[4]); MM.jip_join(T[4])
daemon.CLAN_MATCH[T[4]] = mid; daemon.CLAN_ENDED[mid] = time.time()
caps = []
_ap = daemon.clan.apply_match
daemon.clan.apply_match = lambda *a, **k: (caps.append((a[3], a[4])), _ap(*a, **k))[1]
daemon.clan_report(T[4], 40, 2, {})
daemon.clan.apply_match = _ap
check(caps and caps[-1] == (240, False), "clan day: 40 parts earned + 200 late-join bonus = 240 (%s)" % (caps,))

# ---- a stale LOADED mark of an established player must not block a joiner's GAME-START; an old match's result must not clear it
mid = running(T[:3], mid="new")
MM.matches["old"] = [T[3], T[0], T[1]]; MM.departed["old"] = {T[0], T[1]}      # T[0], T[1] left "old" and play in "new"; T[3] hosted "old"
daemon.LOADED.clear(); daemon.LOADED.update(T[:3])
daemon.loaded_clear_match("old", MM.matches["old"])
check(T[0] in daemon.LOADED and T[1] in daemon.LOADED, "old match's result keeps LOADED of players who already play in another match")
check(T[3] not in daemon.LOADED, "...and clears the one of the player who has no other match")
daemon.LOADED.discard(T[0])                                                     # the stale state: an established player lost its mark
MM.matches.pop("old"); MM.departed.pop("old")
search(T[3]); r = MM.jip_join(T[3]); daemon.JIP = True
daemon.SESSIONS.conn = lambda t: None
daemon.LOADED.add(T[3]); MM.joining[T[3]] = (r[0], time.time() - 60)
daemon.add_matches = lambda *a, **k: None; daemon.clan_match_started = lambda *a, **k: None
check(daemon.maybe_game_start(T[3]) is True and T[3] not in MM.joining, "joiner starts although an established player's LOADED mark is missing")

# no joiner in the first JIP_MIN_AGE s after GAME-START
mid = running(T[:3]); MM.started_t[mid] = time.time(); search(T[3]); why = []
check(MM.jip_join(T[3], why) is None and 'past GAME-START' in ' '.join(why), 'joiner held back right after GAME-START (%s)' % why)
MM.started_t[mid] = time.time() - 30
check(MM.jip_join(T[3], []) is not None, 'joiner accepted 30 s after GAME-START')

# a joiner that backs out at the moment its match is found (leave lands between jip_join and jip_start) is not started
mid = running(T[:3]); MM.started_t[mid] = time.time() - 30; search(T[3])
r = MM.jip_join(T[3], [])
check(r is not None and T[3] in MM.joining, "joiner picked")
daemon.leave_running_match(T[3], "left (0x02)")                 # the back-out arrives before jip_start
check(T[3] not in MM.joining, "back-out removed the joiner from 'joining'")
sent = []
daemon.SESSIONS.conn = lambda t: type("C", (), {"sendall": lambda self, b: sent.append(b)})()
_r = _real_jip_start(T[3], r[0], r[1], r[2])
check(_r is False and not sent, "jip_start does not send START-MATCH to a joiner that left")
check(T[3] not in daemon.JIP_LATE, "no JIP_LATE stamp for it")

# =====================================================================================================================================
# Live: a server-relay match (a Linux client without its Steam helper) was filled to 8 by join in progress with players who
# all had a helper. RELAY_MATCH_MAX: past the limit a joiner WITH a helper is refused (it plays Steam P2P); one without a helper still joins.
# =====================================================================================================================================
class _Conn:
    def sendall(self, b): pass
def _helper(t, sid):
    daemon.BRIDGES.register(t, _Conn(), sid, 7777)
_old_max = daemon.RELAY_MATCH_MAX
daemon.RELAY_MATCH_MAX = 4
for i, t in enumerate(T[1:6]): _helper(t, 76561190000000000 + i)       # T[0] = the Linux host without a helper
mid = running(T[:3])                                                  # relay match (running() marks MATCH_P2P False), 3 active
search(T[3]); why = []
r = MM.jip_join(T[3], why)
check(r is not None, "relay match with 3 players: a joiner with a helper still joins (4 <= limit) (%s)" % why)
search(T[4]); why = []
r = MM.jip_join(T[4], why)
check(r is None and any("server-relay match with 4 players" in w for w in why), "relay match at 4: a joiner with a helper is refused (%s)" % why)
check(T[4] in MM.queue, "the refused joiner stays in the queue (it forms / joins a Steam P2P match)")
del MM.queue[T[4]]
search(T[6]); why = []                                                # T[6] has no helper either: relay anywhere
r = MM.jip_join(T[6], why)
check(r is not None, "relay match at 4: a joiner WITHOUT a helper still joins (%s)" % why)
# the same match marked Steam P2P: the limit does not apply
mid = running(T[:4]); daemon.MATCH_P2P[frozenset(T[:4])] = True
for i, t in enumerate(T[:4]): _helper(t, 76561190000000100 + i)
search(T[4]); why = []
r = MM.jip_join(T[4], why)
check(r is not None, "Steam P2P match with 4 players: a joiner with a helper joins (%s)" % why)
# queue hold: a relay match at its limit does not hold searchers that all have a helper - they form their own (Steam P2P) match
for t in T: daemon.BRIDGES.unregister(t)
for i, t in enumerate(T[1:8]): _helper(t, 76561190000000200 + i)
mid = running(T[:4], left=400); search(T[4]); search(T[5]); MM.last_arrival = time.time() - 600   # past the fill step-down: 2 searchers may form
r = MM.try_form()
check(r[0] is not None and sorted(r[1]) == sorted(T[4:6]), "relay match at 4 + 2 searchers with helpers: they form their own match (%s)" % (r,))
mid = running(T[:3], left=400); search(T[4]); search(T[5]); MM.last_arrival = time.time() - 600
r = MM.try_form()
check(r == (None, None), "relay match at 3 (room for 1 under the limit): the searchers are still held / joined as before")
daemon.RELAY_MATCH_MAX = 0
mid = running(T[:4])
search(T[4]); why = []
r = MM.jip_join(T[4], why)
check(r is not None, "T2R_RELAY_MAX=0: no limit, the relay match takes a 5th player with a helper (%s)" % why)
daemon.RELAY_MATCH_MAX = _old_max
for t in T: daemon.BRIDGES.unregister(t)

print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
