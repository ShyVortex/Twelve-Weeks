"""Private matches (tools/private_lobby.py + the daemon wiring, re/private-lobby-1117.md): lobby / code / rules / teams / pool, the
matchmaker's private formation (members only, never mixed with public searchers), join in progress limits, map choice, no clan / stats effects,
AFK / ping / gun limit switches, the op 0xF8 wire. Offline, plain python, temp DB, no sockets. Run: python tools/tests/test_private_lobby.py"""
import os, sys, tempfile, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]


import private_lobby as P  # noqa: E402

# ------------------------------------------------------------------ pure module
clock = [1000.0]
L = P.Lobbies(nmaps=25, now=lambda: clock[0])
A, B, C, D, E = (tok(n) for n in ("Ann", "Bob", "Cat", "Dan", "Eve"))
lb, err = L.create(A)
check(lb is not None and not err and len(lb.code) == P.CODE_LEN and all(ch in P.CODE_ALPHABET for ch in lb.code), "create: a 5-letter code from the safe alphabet")
check(L.create(A)[0] is lb, "create again = the owner's own lobby")
check(lb.rules == P.defaults() and lb.map == P.MAP_VOTE and lb.pool == (1 << 25) - 1, "defaults: every rule default, map vote, every map in the pool")
check(L.join(B, lb.code.lower())[0] is lb, "join is case-insensitive")
check(L.join(C, "zzzzz") == (None, "nocode"), "unknown code refused")
check(P.norm_code("ab0-1c") == "ABOIC", "code normalising: 0 -> O, 1 -> I, separators dropped")
check(L.set(B, "lives=30")[1] == "notowner", "only the owner sets rules")
check(L.set(A, "lives=30")[1] == "" and lb.rules["lives"] == 30, "owner sets TEAM LIVES 30")
check(L.set(A, "lives=31")[1] == "badrule" and lb.rules["lives"] == 30, "a value outside the table is refused")
check(L.set(A, "nosuch=1")[1] == "badrule", "unknown rule refused")
check(L.set(A, "hp=150")[1] == "badrule", "MAX HEALTH is gone")
check(lb.rules["invuln"] == 0 and lb.rules["downed"] == 1, "INVINCIBILITY off / DOWNED SYSTEM on by default")
check(L.set(A, "invuln=1")[1] == "" and L.set(A, "downed=0")[1] == "" and lb.rules["invuln"] == 1 and lb.rules["downed"] == 0, "INVINCIBILITY on, DOWNED SYSTEM off")
check(L.set(A, "invuln=0")[1] == "" and L.set(A, "downed=1")[1] == "", "and back")
check(L.set(A, "pool=0")[1] == "emptypool", "an empty pool is refused")
check(L.set(A, "map=3")[1] == "" and lb.map == 3, "CHOOSE MAP: a fixed map")
check(L.set(A, "pool=%x" % 0b10011)[1] == "" and lb.map == P.MAP_VOTE, "the chosen map left the pool: back to a vote")
check(L.set(A, "map=7")[1] == "" and lb.pool >> 7 & 1, "a chosen map joins the pool")
check(L.set(A, "map=-2")[1] == "" and lb.map == P.MAP_RANDOM, "random from the pool")
check(L.set_team(A, "1=0")[1] == "teamsauto", "teams BALANCED: no team picks")
L.set(A, "teams=2")
check(L.set_team(B, "1=1")[1] == "" and lb.team[B] == 1, "PLAYERS PICK: a member picks its own team")
check(L.set_team(B, "0=1")[1] == "notallowed", "PLAYERS PICK: not another player's team")
L.set(A, "teams=1")
check(L.set_team(B, "1=0")[1] == "notallowed" and L.set_team(A, "1=0")[1] == "" and lb.team[B] == 0, "HOST ASSIGNS: only the owner")
check(L.set_team(A, "1=255")[1] == "" and B not in lb.team, "255 = automatic")
t0, t1 = L.teams_for(lb, [A, B, C], lambda pl: (pl[0::2], pl[1::2]))
check(len(t0) + len(t1) == 3 and abs(len(t0) - len(t1)) <= 1, "automatic players fill the smaller team")
st = L.state_text(B, lambda t: "Bob Smith" if t == B else "Ann")
check("in=1" in st and "own=0" in st and "me=1" in st and "p1=Bob_Smith" in st and "lives=30" in st and "h0=1" in st, "state text: " + st[:120])
check(L.state_text(D, lambda t: "") == "ok=1 in=0", "not in a lobby")
# kick / leave / owner hand-over
L.join(C, lb.code)
check(L.kick(B, "2")[1] == "notowner" and L.kick(A, "0")[1] == "badvalue", "kick: owner only, never itself")
check(L.kick(A, "2")[1] == "" and C not in lb.members and not L.in_lobby(C), "owner kicks member 2")
L.leave(A)
check(lb.owner == B and lb.members == [B], "owner left: the oldest member owns it")
L.leave(B)
check(lb.code not in L.by_code, "last one out closes the lobby")
# full / max players
lb, _ = L.create(A)
L.set(A, "maxp=2")
L.join(B, lb.code)
check(L.join(C, lb.code) == (None, "full"), "MAX PLAYERS 2: a third join is refused")
# start / launch
check(L.start(B)[1] == "notowner", "only the owner starts")
check(L.start(A)[1] == "" and lb.state == 1 and lb.go == 1, "START: launching, go counter up")
check(L.set(A, "lives=10")[1] == "busy", "rules locked while launching")
check(L.launches([A]) == [], "not every member searches yet: no match")
check(L.launches([A, B]) == [(lb, [A, B])], "every member searches: the match forms")
clock[0] += P.LAUNCH_WAIT_S + 1
check(L.launches([A]) == [(lb, [A])], "after LAUNCH_WAIT_S the members that search play")
L.bound(lb, "m1", [A, B])
check(lb.state == 2 and L.is_private_mid("m1") and L.rule("m1", "maxp") == 2 and L.rule("public", "maxp") is None, "bound: rules of the match")
check(L.jip_ok(A, "m1") and not L.jip_ok(D, "m1"), "join in progress: only lobby members")
check(not L.jip_ok(A, "pub"), "a lobby member never joins a public match")
check(L.jip_ok(D, "pub"), "a public player joins public matches")
lb.rules["late"] = 0
check(L.rules_of_mid("m1")["late"] == 1, "match rules are a copy at the start")
L.match_over("m1")
check(lb.state == 0, "match over: the lobby is back")
L.start(A); L.bound(lb, "m2", [A, B]); L.aborted("m2")
check(lb.state == 1 and lb.launch_members == [A, B], "a called-off match launches the lobby again")
lb.state = 0
check(L.on_enqueue(B) and not L.in_lobby(B), "a public search leaves a lobby that is not launching")
check("pm=1" in L.rules_text("m1") and "lives=" in L.rules_text("m1") and L.rules_text(None) == "pm=0", "rules text")
# gc
clock[0] += P.MEMBER_TTL + 1
L.touch(A)
L.join(D, lb.code)
clock[0] += P.MEMBER_TTL + 1
L.touch(A)
check(L.gc() == 1 and not L.in_lobby(D) and L.in_lobby(A), "a member that stopped polling leaves")
for _ in range(int(P.LOBBY_IDLE_S / (P.MEMBER_TTL - 1)) + 2):   # 1 h+ on the lobby page with no change, A still polling
    clock[0] += P.MEMBER_TTL - 1
    L.touch(A)
    L.gc()
check(L.in_lobby(A), "a lobby whose members still poll stays open past LOBBY_IDLE_S")
pl = A.encode() + bytes([1, P.S_SET]) + b"lives=40"
check(P.Lobbies.parse(pl) == (A, P.S_SET, "lives=40"), "op payload parsed")
check(P.Lobbies.parse(b"short") is None, "short payload refused")
for k, (dflt, vals, label) in P.RULES.items():
    check(dflt in vals and label.isupper(), "rule %s: default %s is a listed value" % (k, dflt))
check(sorted(k for _, ks in P.RULE_TABS for k in ks) == sorted(P.RULES), "every rule is on one tab")

# ------------------------------------------------------------------ daemon wiring
NAMES = ["Jay", "PlayerA", "PlayerB", "PlayerC", "PlayerD", "PlayerE"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_FILL_WAIT="0", T2R_QUEUE_SETTLE="0", T2R_P2P="0", T2R_MAP_VOTE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
for t in T:
    daemon.PRES.touch(t, "x")
MM = daemon.MM
LOGS = []
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
daemon.PRIV.log = daemon.log
daemon.fill_rule = lambda: "classic"           # FILL_WAIT 0: the minimum lobby forms at once


def op(t, sub, arg=""):
    rep = daemon.priv_op(t.encode() + bytes([1, sub]) + arg.encode())
    body = rep[3:].decode()
    return dict(kv.split("=", 1) for kv in body.split() if "=" in kv)


def qput(i):
    now = time.time(); MM.queue[T[i]] = now; MM.seen[T[i]] = now; MM.settle[T[i]] = 0


r = op(T[0], P.S_CREATE)
code = r["code"]
check(r["ok"] == "1" and r["in"] == "1" and r["own"] == "1" and "av" in r, "op CREATE: lobby + allowed maps")
r = op(T[1], P.S_JOIN, code)
check(r["n"] == "2" and r["me"] == "1" and r["p1"] == "PlayerA", "op JOIN: two members")
check(op(T[1], P.S_SET, "lives=10")["err"] == "notowner", "op SET by a member refused")
op(T[0], P.S_SET, "lives=40"); op(T[0], P.S_SET, "mode=1"); op(T[0], P.S_SET, "afk=0"); op(T[0], P.S_SET, "glim=0")
# public searchers + the lobby members searching BEFORE start: the members leave their lobby (public search)
qput(2); qput(3)
mid, pl = MM.enqueue(T[4])
check(mid is not None and T[0] not in pl and T[1] not in pl, "public match forms without the lobby members")
for t in pl:
    MM.queue.pop(t, None)
MM.matches.clear()
r = op(T[0], P.S_START)
check(r["st"] == "1" and r["go"] == "1", "op START: launching")
qput(0)
check(MM.try_form()[0] is None, "one member searching: wait for the other")
qput(1); qput(5)
mid, pl = MM.try_form()
check(mid is not None and sorted(pl) == sorted(T[:2]) and T[5] in MM.queue, "private match = the lobby members only (the public searcher stays queued)")
check(daemon.PRIV.is_private_mid(mid) and daemon.MODEQ.match_mode(mid) == "interrogation", "private match bound, mode = the lobby's MODE")
check(op(T[0], P.S_STATE)["st"] == "2", "lobby state: in a match")
r = op(T[1], P.S_RULES)
check(r["pm"] == "1" and r["lives"] == "40" and r["mode"] == "1", "op RULES in the match: " + str(r))
check(op(T[5], P.S_RULES) == {"pm": "0"}, "op RULES of a non-private player: pm=0")
# map choice
daemon.MATCH_MAP.clear(); daemon.VOTES.clear()
idx, opts = daemon.priv_pick_map(mid, pl)
check(opts is not None and idx in opts and len(opts) <= 20, "map VOTE: a vote over the private pool")
daemon.PRIV.mid_rules[mid]["map"] = 2
check(daemon.priv_pick_map(mid, pl) == (2, None), "a chosen map is played (no vote)")
daemon.PRIV.mid_rules[mid]["map"] = -2
daemon.PRIV.mid_rules[mid]["pool"] = 0b1100
daemon.PRIV.mid_rules[mid]["mode"] = 0
check(daemon.priv_pick_map(mid, pl)[0] in (2, 3) and daemon.priv_pick_map(mid, pl)[1] is None, "RANDOM: one map of the pool")
# switches
check(daemon.PRIV.rule(mid, "afk") == 0 and daemon.PRIV.rule(mid, "glim") == 0, "AFK REMOVAL / GUN LIMITS off for this match")
wb = daemon.wave_byte(mid=mid)
check(wb & 0x40 and wb & 1, "wave byte: no AFK removal (0x40), waves on (RESPAWN TIMER 0)")
daemon.PRIV.mid_rules[mid]["resp"] = 5
check(not daemon.wave_byte(mid=mid) & 1, "RESPAWN TIMER 5 s: waves off on the wave byte")
check(daemon.wave_byte() & 0x40 == (0x40 if daemon.AFK_KICK_S <= 0 else 0), "public wave byte unchanged")
# clan / stats
daemon.clan_match_started(pl, mid)
check(all(t not in daemon.CLAN_MATCH for t in pl) and all(daemon.PRIV_LAST_MID.get(t) == mid for t in pl), "no clan match booked for a private match")
LOGS.clear()
daemon.clan_report(pl[0], 500, 1)
check(any("private match" in l and "not booked" in l for l in LOGS), "clan report of a private match: answered, not booked")
LOGS.clear()
daemon.record_result(pl, 0, mid=mid)
check(any("RESULT private match" in l for l in LOGS), "no wins / skill rating for a private match")
# join in progress: only members
MM.started.add(mid); MM.launched.add(mid)
check(not daemon.PRIV.jip_ok(T[5], mid) and daemon.PRIV.jip_ok(T[1], mid), "join in progress: strangers refused, members allowed")
# end: lobby back
MM.end(mid)
check(op(T[0], P.S_STATE)["st"] == "0", "match end: the lobby is back for the next start")
r = op(T[1], P.S_LEAVE)
check(r["in"] == "0" and op(T[0], P.S_STATE)["n"] == "1", "op LEAVE")
daemon.PRIVATE_ON = False
check(op(T[0], P.S_STATE)["err"] == "off", "T2R_PRIVATE=0: refused")
daemon.PRIVATE_ON = True

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
