"""Offline tests for the friends + party system (tools/social.py + its daemon wiring): friend requests (send / accept / decline / cancel / remove / duplicates /
limits), presence statuses, name + Steam id search, party leader rules (invite / join / leave / kick / promote / timeout), in-game notes (EN / PL), the real op
0xD8 over TCP, and party matchmaking: a party lands on one team, is never split, waits until every member searches, waits when too big for the open slots,
mixes with solo players, and a leader that leaves disbands it.
Run: python tools/tests/test_social.py   (free localhost port, temp DB)."""
import contextlib, json, os, socket, sqlite3, struct, sys, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import social  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (b"T2N:".hex() + name.encode().hex() + "00" + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina", "Hal", "Ivan"]
T = {n: tok(n) for n in NAMES}
SID = {n: 76561198000000000 + i for i, n in enumerate(NAMES)}

# ------------------------------------------------------------ fake host
class Host:
    def __init__(self):
        self.t = 1000.0
        self.path = os.path.join(tempfile.mkdtemp(), "social.db")
        self.sids = {}              # token -> steam id
        self.names = {}             # token -> shown name
        self.game = set()           # tokens present in game
        self.mm = {}                # token -> match / search
        c = sqlite3.connect(self.path)
        c.execute("CREATE TABLE players(token TEXT PRIMARY KEY, name TEXT, loadout BLOB, steamid INTEGER DEFAULT 0, last_seen REAL)")
        c.execute("CREATE TABLE names(token_id TEXT PRIMARY KEY, name TEXT, tag TEXT, updated REAL)")
        c.commit(); c.close()
    def now(self): return self.t
    def log(self, *a): pass
    @contextlib.contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        try:
            yield c
            c.commit()
        finally:
            c.close()
    def steamid(self, t): return self.sids.get(t, 0)
    def name(self, t): return self.names.get(t)
    def game_tokens(self): return list(self.game)
    def alive_tokens(self): return set(self.game) | set(self.mm)
    def mm_state(self, t): return self.mm.get(t)
    def player(self, n, steam=True, game=False):
        t = T[n]
        self.names[t] = n
        if steam: self.sids[t] = SID[n]
        if game: self.game.add(t)
        with self.db() as c:
            c.execute("INSERT OR REPLACE INTO players(token,name,steamid,last_seen) VALUES(?,?,?,?)", (t, n, self.sids.get(t, 0), self.t))
        return t

H = Host()
PA = social.Parties(max_size=4, now=H.now)
S = social.Social(H, PA)
def call(who, sub, arg="", lang=0):
    S._om = (0.0, {}, set())
    return S.handle(T[who], lang, sub, arg)
def key(n): return "s:%d" % SID[n]
for n in NAMES: H.player(n)

# ------------------------------------------------------------ friends: requests, pending lists, accept
r = call("Alice", social.S_STATE)
check(r["ok"] == 1 and r["friends"] == [] and r["in"] == [] and r["out"] == [] and r["party"] is None and r["me"]["id"] == key("Alice"), "fresh state is empty")
call("Bob", social.S_STATE)             # (Bob is online: in-game lines only reach online tokens)
r = call("Alice", social.S_ADD, "Bob")
check(r["ok"] == 1 and [o["name"] for o in r["out"]] == ["Bob"], "Alice asks Bob by name: outgoing request listed")
r = call("Bob", social.S_STATE)
check([i["name"] for i in r["in"]] == ["Alice"] and r["friends"] == [], "Bob sees the incoming request")
check(any("friend request" in x[3] for x in S.notes_for(T["Bob"], 0)), "Bob gets an in-game line about it (EN)")
check(any("zaproszenie do znajomych" in x[3] for x in S.notes_for(T["Bob"], 1)), "... and in Polish")
check(S.notes_for(T["Bob"], 0)[0][1] == "p" and S.notes_for(T["Bob"], 0)[0][0] > social.NOTE_BASE, "note = kind p with a high unique id")
r = call("Alice", social.S_ADD, key("Bob"))
check(r["ok"] == 0 and r["err"] == "pending", "asking twice -> pending")
r = call("Alice", social.S_ADD, "Alice")
check(r["ok"] == 0 and r["err"] == "self", "yourself refused")
r = call("Alice", social.S_ADD, "Nobody Here")
check(r["ok"] == 0 and r["err"] == "unknown", "unknown name refused")
r = call("Bob", social.S_ACCEPT, key("Alice"))
check(r["ok"] == 1 and [f["name"] for f in r["friends"]] == ["Alice"] and r["in"] == [], "Bob accepts: friends, pending gone")
r = call("Alice", social.S_STATE)
check([f["name"] for f in r["friends"]] == ["Bob"] and r["out"] == [], "Alice sees Bob as a friend")
check(any("accepted" in x[3] for x in S.notes_for(T["Alice"], 0)), "Alice is told in game")
r = call("Alice", social.S_ADD, "Bob")
check(r["err"] == "already", "already friends")
# decline / cancel / unfriend
call("Carol", social.S_ADD, "Alice")
r = call("Alice", social.S_REMOVE, key("Carol"))
check(r["ok"] == 1 and r["in"] == [], "Alice declines Carol's request")
call("Carol", social.S_ADD, str(SID["Dave"]))
r = call("Carol", social.S_STATE)
check([o["name"] for o in r["out"]] == ["Dave"], "request by Steam id")
r = call("Carol", social.S_REMOVE, key("Dave"))
check(r["out"] == [], "Carol cancels the outgoing request")
call("Eve", social.S_ADD, "Frank"); r = call("Frank", social.S_ADD, "Eve")
check([f["name"] for f in r["friends"]] == ["Eve"], "both asked each other -> friends at once")
r = call("Frank", social.S_REMOVE, key("Eve"))
check(r["friends"] == [] and call("Eve", social.S_STATE)["friends"] == [], "unfriend removes it on both sides")
r = call("Alice", social.S_ACCEPT, key("Gina"))
check(r["err"] == "expired", "accepting a request nobody sent -> expired")
r = call("Alice", social.S_REMOVE, "garbage")
check(r["err"] == "bad", "malformed id refused")

# ------------------------------------------------------------ search
r = call("Alice", social.S_SEARCH, "gin")
check([f["name"] for f in r["found"]] == ["Gina"] and r["found"][0]["rel"] == "", "search by name prefix")
r = call("Alice", social.S_SEARCH, "bo")
check(r["found"][0]["rel"] == "friend", "search marks existing friends")
r = call("Alice", social.S_SEARCH, str(SID["Hal"]))
check([f["name"] for f in r["found"]] == ["Hal"], "search by Steam id")
check(call("Alice", social.S_SEARCH, "a")["found"] == [], "one letter finds nothing")
check(all(f["id"] != key("Alice") for f in call("Alice", social.S_SEARCH, "al")["found"]), "never finds yourself")
check(call("Alice", social.S_SEARCH, "%%")["found"] == [], "LIKE wildcards are literal")

# ------------------------------------------------------------ presence
H.game.add(T["Bob"]); H.t += 5
r = call("Alice", social.S_STATE)
check(r["friends"][0]["name"] == "Bob" and r["friends"][0]["status"] == "menu", "Bob in the game menu")
H.mm[T["Bob"]] = "search"; r = call("Alice", social.S_STATE)
check(r["friends"][0]["status"] == "search", "Bob searching")
H.mm[T["Bob"]] = "match"; r = call("Alice", social.S_STATE)
check(r["friends"][0]["status"] == "match", "Bob in a match")
H.mm.clear(); H.game.clear(); H.t += social.PRESENCE_TTL + 1
r = call("Alice", social.S_STATE)
check(r["friends"][0]["status"] == "off" and r["friends"][0]["seen"] is not None, "Bob offline with a last seen")
call("Bob", social.S_STATE)
r = call("Alice", social.S_STATE)
check(r["friends"][0]["status"] == "launcher", "Bob's launcher poll = online (launcher)")
H.t += social.PRESENCE_TTL + 1
r = call("Alice", social.S_STATE)
check(r["friends"][0]["status"] == "off", "launcher silent > 60 s = offline again")
# order: online first
call("Gina", social.S_ADD, "Alice"); call("Alice", social.S_ACCEPT, key("Gina")); H.t += 1
call("Gina", social.S_STATE)
r = call("Alice", social.S_STATE)
check([f["name"] for f in r["friends"]] == ["Gina", "Bob"], "online friends listed before offline ones")

# ------------------------------------------------------------ steam id learned later: the install account's friends follow
ti = T["Ivan"]; H.sids.pop(ti)
call("Ivan", social.S_ADD, "Alice")
r = call("Ivan", social.S_STATE)
check(r["me"]["id"].startswith("t:") and [o["name"] for o in r["out"]] == ["Alice"], "no Steam id yet: install account")
H.sids[ti] = SID["Ivan"]
r = call("Ivan", social.S_STATE)
check(r["me"]["id"] == key("Ivan") and [o["name"] for o in r["out"]] == ["Alice"], "Steam id learned: pending request moved to the Steam account")
call("Ivan", social.S_REMOVE, key("Alice"))

# ------------------------------------------------------------ limits + rate
H.t += 120
for i in range(social.REQUEST_MAX + 3):
    with H.db() as c:
        c.execute("INSERT OR REPLACE INTO social_friends(a,b,state,since) VALUES(?,?,0,?)", (key("Hal"), "s:%d" % (7000 + i), H.t)) if i < social.REQUEST_MAX else None
r = call("Hal", social.S_ADD, str(SID["Alice"]))
check(r["ok"] == 0 and r["err"] == "limit", "too many open requests -> limit")
H.t += 120
r = None
for i in range(social.OPS_PER_MIN + 2):
    r = call("Dave", social.S_REMOVE, "s:1")
check(r["err"] == "rate", "write flood from one account is rate limited")
H.t += 61

# ------------------------------------------------------------ parties (token level)
P = social.Parties(max_size=4, now=H.now)
a, b, c_, d, e = [T[n] for n in ("Alice", "Bob", "Carol", "Dave", "Eve")]
check(P.invite_token(a, a) == "self", "party: no self invite")
check(P.invite_token(a, b) is None and P.pid(a) is None, "invite alone creates no party")
pid, err = P.accept_token(b, a)
check(err is None and P.pid(a) == P.pid(b) and P.leader(b) == a and P.is_leader(a) and not P.is_leader(b), "accept: inviter leads")
check(P.invite_token(b, c_) == "notleader", "a member cannot invite")
check(P.accept_token(c_, a)[1] == "expired", "no invitation, no join")
P.invite_token(a, c_); P.invite_token(a, d); P.accept_token(c_, a); P.accept_token(d, a)
check(P.size(a) == 4, "four in the party")
check(P.invite_token(a, e) == "full", "party full at team size")
check(P.kick(b, c_) == "notleader", "a member cannot kick")
check(P.kick(a, c_) is None and P.pid(c_) is None and P.size(a) == 3, "leader kicks")
ev = P.drain()
check(("%s" % c_, "pkick", None) in [(x[0], x[1], x[2]) for x in ev], "kicked player gets a note event")
check(P.promote(a, b) is None and P.leader(a) == b, "leader promotes Bob")
check(P.promote(a, d) == "notleader", "old leader can no longer promote")
check(P.leave(b) and P.pid(a) is None and P.pid(d) is None, "leader leaves -> party disbanded (a promoted leader was needed to keep it)")
P.invite_token(a, b); P.accept_token(b, a); P.invite_token(a, c_); P.accept_token(c_, a); P.promote(a, b)
P.leave(a)
check(P.pid(b) == P.pid(c_) and P.leader(b) == b and P.size(b) == 2, "old leader leaves after promoting: party lives on")
P.leave(c_)
check(P.pid(b) is None, "a party of one is no party")
P.invite_token(a, b); P.accept_token(b, a); P.invite_token(a, c_); P.accept_token(c_, a)
P.gc({b, c_}, H.t)
check(P.leader(b) == b and P.size(b) == 2, "leader gone offline: next member leads")
P.gc({b}, H.t)
check(P.pid(b) is None, "last mate gone: party gone")
P.invite_token(a, b); H.t += social.INVITE_TTL + 1
check(P.accept_token(b, a)[1] == "expired", "invitation expires")
P.invite_token(a, b); P.invite_token(c_, b); P.accept_token(b, a)
P.invite_token(c_, d); P.accept_token(d, c_); P.invite_token(c_, b)
check(P.accept_token(b, c_)[1] is None and P.pid(b) == P.pid(c_) and P.pid(a) is None, "joining another party leaves the old one (and a leader's departure disbanded it)")
# pure helpers
Q = social.Parties(max_size=4)
Q.of.update({"a": "p", "b": "p", "c": "p"}); Q.leaders["p"] = "a"
ok, held = social.held_parties(["x", "a", "b", "y"], Q)
check(ok == ["x", "y"] and held == {"p": ["c"]}, "held_parties: an incomplete party is held back as a whole")
ok, held = social.held_parties(["a", "x", "b", "c"], Q)
check(ok == ["a", "x", "b", "c"] and not held, "complete party passes")
check(social.pick_units(["a", "x", "b", "c", "y"], Q, 8) == ["a", "b", "c", "x", "y"], "pick_units: party is one unit at its first member's place")
check(social.pick_units(["a", "b", "c", "x"], Q, 8) == ["x"], "party of 3 + 1 single would be 3v1: the party waits")
check(social.pick_units(["a", "b", "c", "x", "y"], Q, 8) == ["a", "b", "c", "x", "y"], "party of 3 + 2 singles = 3v2 fine")
check(social.pick_units(["x", "y", "z", "w", "v", "a", "b", "c"], Q, 6) == ["x", "y", "z", "w", "v"] or social.pick_units(["x", "y", "z", "w", "v", "a", "b", "c"], Q, 6) == ["x", "y", "z", "w", "v"],
      "party that does not fit the open slots waits")
check(social.pick_units(["a", "b", "c", "x", "y", "z", "w"], Q, 6) == ["a", "b", "c", "x", "y", "z"], "slots used in queue order, the party stays whole")

# ------------------------------------------------------------ parties (account level, launcher ops)
H.game.clear(); H.mm.clear(); H.t += 200
S.p = social.Parties(max_size=4, now=H.now)
for n in ("Alice", "Bob", "Carol", "Gina"):
    call(n, social.S_STATE)
r = call("Alice", social.S_INVITE, key("Carol"))
check(r["err"] == "notfriend", "party invites go to friends only")
r = call("Alice", social.S_INVITE, key("Bob"))
check(r["ok"] == 1 and r["party"] is None, "invite sent, no party yet")
r = call("Bob", social.S_STATE)
check([p["name"] for p in r["pinv"]] == ["Alice"], "Bob sees the party invite")
check(any("invited you to a party" in x[3] for x in S.notes_for(T["Bob"], 0)), "in-game line for the invite")
r = call("Bob", social.S_JOIN, key("Alice"))
check(r["ok"] == 1 and r["party"] and r["party"]["meLeader"] is False and [m["name"] for m in r["party"]["members"]] == ["Alice", "Bob"]
      and r["party"]["members"][0]["leader"], "Bob joins: Alice (leader) first")
r = call("Alice", social.S_STATE)
check(r["party"]["meLeader"] and r["party"]["max"] == 4, "Alice is the leader")
r = call("Bob", social.S_INVITE, key("Gina"))
check(r["err"] in ("notfriend", "notleader"), "member cannot invite")
r = call("Bob", social.S_READY, "1")
check([m["ready"] for m in r["party"]["members"]] == [True, True], "ready flag (the leader always counts as ready)")
r = call("Bob", social.S_READY, "0")
check([m["ready"] for m in r["party"]["members"]] == [True, False], "UNREADY clears it")
check(r["party"]["lsearch"] is False, "leader not searching: lsearch false")
check(S.search_gate(T["Bob"], lambda m: False) is True, "member's FIND MATCH while the leader does not search is a ready toggle, not a queue")
check(S.search_gate(T["Alice"], lambda m: False) is True, "the leader is held while a mate is not ready")
check(S.search_gate(T["Alice"], lambda m: m == T["Bob"]) is False, "... but not when that mate already searches")
S.p.set_ready(T["Bob"], True)
check(S.search_gate(T["Alice"], lambda m: False) is False, "the leader searches once everyone is ready")
S.p.set_ready(T["Bob"], False)
check(S.search_gate(T["Bob"], lambda m: m == T["Alice"]) is False, "a member is let in once the leader searches")
H.mm[T["Alice"]] = "search"
check(call("Bob", social.S_STATE)["party"]["lsearch"] is True, "lsearch follows the leader's search")
H.mm.pop(T["Alice"], None)
call("Bob", social.S_READY, "1")
S.p.clear_ready([T["Bob"]])
check([m["ready"] for m in call("Bob", social.S_STATE)["party"]["members"]] == [True, False], "clear_ready: a formed match resets the flags")
call("Bob", social.S_READY, "1")
r = call("Bob", social.S_KICK, key("Alice"))
check(r["err"] == "notleader", "member cannot kick")
r = call("Alice", social.S_PROMOTE, key("Bob"))
check(r["party"]["leader"] == key("Bob") and not r["party"]["meLeader"], "promote")
r = call("Bob", social.S_KICK, key("Alice"))
check(r["ok"] == 1 and r["party"] is None, "new leader kicks Alice -> party of one is gone")
check(any("removed" in x[3] for x in S.notes_for(T["Alice"], 0)), "Alice was told")
call("Alice", social.S_INVITE, key("Bob")); call("Bob", social.S_DECLINE, key("Alice"))
check(call("Bob", social.S_STATE)["pinv"] == [], "decline drops the invite")
r = call("Bob", social.S_JOIN, key("Alice"))
check(r["err"] == "expired", "joining a declined invite -> expired")
call("Alice", social.S_INVITE, key("Bob")); call("Bob", social.S_JOIN, key("Alice")); r = call("Bob", social.S_LEAVE)
check(r["party"] is None and call("Alice", social.S_STATE)["party"] is None, "member leaves a party of 2 -> it dissolves")
check(any("disbanded" in x[3] for x in S.notes_for(T["Alice"], 0)), "leader told that it dissolved")
# leader queues -> members get a note
call("Alice", social.S_INVITE, key("Bob")); call("Bob", social.S_JOIN, key("Alice"))
S.notes.clear(); S.qnote.clear()
n = S.on_queue(T["Alice"], lambda m: False)
check(n == 1 and any("leader Alice is searching" in x[3] for x in S.notes_for(T["Bob"], 0)), "leader's FIND MATCH tells the members to follow")
check(S.on_queue(T["Alice"], lambda m: False) == 0, "... not again within 20 s")
S.notes.clear()
check(S.on_queue(T["Bob"], lambda m: False) == 0, "a member's FIND MATCH is a READY UP: no note to the leader")
S.qnote.clear(); S.notes.clear(); S.p.set_ready(T["Bob"], True)
check(S.on_queue(T["Alice"], lambda m: False) == 0, "a ready member follows the leader by himself: no 'press READY UP' note")
H.t += 40; S.notes.clear()
check(S.on_queue(T["Alice"], lambda m: m == T["Bob"]) == 0, "nobody to tell when the members already search")
check([r[1] for r in S.party_rows(T["Alice"])] == ["Bob"], "party_rows lists the mates")

# ------------------------------------------------------------ privacy + offline members
r = call("Alice", social.S_SEARCH, "gin")
check(r["found"][0]["rel"] == "friend" or r["found"][0]["status"] == "", "search shows presence of friends only")
r = call("Alice", social.S_SEARCH, "hal")
check(r["found"][0]["rel"] == "" and r["found"][0]["status"] == "", "a stranger's presence is not shown: " + str(r["found"][0]))
H.game.clear(); H.mm.clear(); H.t += 500
S.p = social.Parties(max_size=4, now=H.now)
S.hb.clear(); S.gone.clear(); S._pt_at = 0.0
for n in ("Alice", "Bob", "Carol"):
    H.game.add(T[n])
a, b, c_ = T["Alice"], T["Bob"], T["Carol"]
S.p.invite_token(a, b); S.p.accept_token(b, a); S.p.invite_token(a, c_); S.p.accept_token(c_, a)
check(S.party_tick(H.t) == 0 and S.p.size(a) == 3, "everybody in the game: the party is untouched")
H.game.discard(a); H.t += 11
S.party_tick(H.t)
check(S.p.size(b) == 3 and S.p.leader(b) == a, "the leader is missing for less than the grace time: still the leader")
H.t += social.PARTY_GRACE + 1
S.party_tick(H.t)
check(S.p.size(b) == 2 and S.p.leader(b) in (b, c_) and S.p.pid(a) is None, "leader offline for 45 s: the party goes on with the next member leading")
check(any("leader now" in x[3] for x in S.notes_for(b, 0)), "... and the members are told who leads")
H.game.discard(c_); H.t += 11; S.party_tick(H.t); H.t += social.PARTY_GRACE + 1; S.party_tick(H.t)
check(S.p.pid(b) is None, "the last mate offline: the party is gone, nobody is held for it")
S.hb[a] = H.t; S.p.invite_token(b, a); H.t += 11; S.party_tick(H.t)
check(S.p.invites_for(a) != [], "a launcher-only invitee stays alive for the party tick")

# ------------------------------------------------------------ private messages (friends only)
H.t += 120
check(call("Alice", social.S_STATE)["friends"][0]["name"] == "Bob", "(Alice + Bob are friends)")
r = call("Alice", social.S_MSG, key("Bob") + "\nhi bob")
check(r["ok"] == 1 and r["chat"]["with"] == key("Bob") and [(m["me"], m["t"]) for m in r["chat"]["msgs"]] == [(True, "hi bob")], "Alice messages Bob: the reply carries the chat")
check(r["unread"] == {}, "the sender has nothing unread")
r = call("Bob", social.S_STATE)
check(r["unread"] == {key("Alice"): 1}, "Bob's state counts 1 unread from Alice: " + str(r["unread"]))
r = call("Bob", social.S_CHAT, key("Alice"))
check(r["ok"] == 1 and [(m["me"], m["t"]) for m in r["chat"]["msgs"]] == [(False, "hi bob")] and r["unread"] == {}, "Bob opens the chat: message shown, marked read")
r = call("Bob", social.S_MSG, key("Alice") + "\nhey\nsecond line \x07 bell \u202e flip \u200b")
check(r["chat"]["msgs"][-1]["t"] == "hey second line bell flip", "newlines / control / bidi characters become spaces: " + repr(r["chat"]["msgs"][-1]["t"]))
r = call("Bob", social.S_MSG, key("Alice") + "\n" + "x" * 300)
check(len(r["chat"]["msgs"][-1]["t"]) == social.MSG_LEN, "long message cut to MSG_LEN")
r = call("Bob", social.S_MSG, key("Alice") + "\n   \x01 ")
check(r["ok"] == 0 and r["err"] == "bad", "empty message refused")
r = call("Alice", social.S_MSG, key("Hal") + "\nhello stranger")
check(r["ok"] == 0 and r["err"] == "notfriend" and "chat" not in r, "message to a non-friend refused")
r = call("Alice", social.S_CHAT, key("Hal"))
check(r["err"] == "notfriend" and "chat" not in r, "chat with a non-friend refused")
r = call("Alice", social.S_MSG, "garbage\nhi")
check(r["err"] == "bad", "malformed id refused")
with H.db() as c:
    check(c.execute("SELECT COUNT(*) FROM social_msgs WHERE a=? AND b=?", (key("Alice"), key("Hal"))).fetchone()[0] == 0, "nothing stored for the refused message")
H.t += 61
oks = [call("Alice", social.S_MSG, key("Bob") + "\nflood %d" % i)["ok"] for i in range(social.MSG_PER_MIN + 2)]
check(oks[:social.MSG_PER_MIN] == [1] * social.MSG_PER_MIN and oks[-1] == 0, "more than MSG_PER_MIN messages a minute -> rate")
H.t += 61
check(call("Alice", social.S_MSG, key("Bob") + "\nafter a minute")["ok"] == 1, "a minute later sending works again")
for i in range(social.MSG_KEEP + 30):
    if i % 15 == 0: H.t += 61
    call("Bob" if i % 2 else "Alice", social.S_MSG, (key("Alice") if i % 2 else key("Bob")) + "\nkeep %d" % i)
with H.db() as c:
    n = c.execute("SELECT COUNT(*) FROM social_msgs WHERE (a=? AND b=?) OR (a=? AND b=?)", (key("Alice"), key("Bob"), key("Bob"), key("Alice"))).fetchone()[0]
check(n == social.MSG_KEEP, "a pair keeps its newest MSG_KEEP messages: %d" % n)
r = call("Alice", social.S_CHAT, key("Bob"))
check(len(r["chat"]["msgs"]) == social.CHAT_SHOW and r["chat"]["msgs"][-1]["t"] == "keep %d" % (social.MSG_KEEP + 29), "chat shows the newest CHAT_SHOW, oldest first")
H.t += 61
for i in range(15):
    call("Alice", social.S_MSG, key("Bob") + "\n" + "\U0001F600" * social.MSG_LEN)
r = call("Bob", social.S_CHAT, key("Alice"))
check(len(social.reply_json(r)) < 40000 and r["chat"]["msgs"][-1]["t"].startswith("\U0001F600"), "emoji-heavy history stays well under the u16 frame: %d bytes" % len(social.reply_json(r)))
# age purge (hourly) + unfriend wipes the pair
H.t += social.MSG_AGE_S + 10
S._mgc_at = 0.0
r = call("Alice", social.S_MSG, key("Bob") + "\nnew month")
check([m["t"] for m in r["chat"]["msgs"]] == ["new month"], "messages older than MSG_AGE_S are deleted")
r = call("Bob", social.S_REMOVE, key("Alice"))
with H.db() as c:
    n = c.execute("SELECT COUNT(*) FROM social_msgs WHERE (a=? AND b=?) OR (a=? AND b=?)", (key("Alice"), key("Bob"), key("Bob"), key("Alice"))).fetchone()[0]
check(r["ok"] == 1 and n == 0, "unfriending deletes the pair's messages")
call("Alice", social.S_ADD, "Bob"); call("Bob", social.S_ACCEPT, key("Alice"))
r = call("Alice", social.S_CHAT, key("Bob"))
check(r["ok"] == 1 and r["chat"]["msgs"] == [] and r["friends"][0]["name"] == "Bob", "friends again: the chat starts empty")

# ------------------------------------------------------------ the daemon: op 0xD8 over TCP + matchmaking
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_FILL_RULE="classic")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)
DT = [tok("P%d" % i) for i in range(10)]
DN = {t: "P%d" % i for i, t in enumerate(DT)}
for i, t in enumerate(DT):
    daemon.set_steam(t, 76561198100000000 + i, DN[t])
    daemon.PRES.touch(t, DN[t])
MM = daemon.MM
PT = daemon.PARTIES

def req(op, payload):
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(struct.pack("<H", len(payload) + 1) + bytes([op]) + payload)
    data = b""
    while len(data) < 2 or len(data) < 2 + struct.unpack_from("<H", data)[0]:
        b = c.recv(65536)
        if not b: break
        data += b
    c.close()
    ln = struct.unpack_from("<H", data)[0]
    return data[2], data[3:2 + ln]
def sreq(i, sub, arg="", lang=0):
    op, body = req(0xD8, DT[i].encode() + bytes([1, lang, sub]) + arg.encode())
    assert op == 0xD9, hex(op)
    return json.loads(body.decode("utf-8"))
def dk(i): return "s:%d" % (76561198100000000 + i)

r = sreq(0, social.S_STATE)
check(r["ok"] == 1 and r["me"]["name"] == "P0" and r["friends"] == [], "TCP: state")
r = sreq(0, social.S_ADD, "P1")
check(r["ok"] == 1 and r["out"][0]["name"] == "P1", "TCP: friend request by name")
r = sreq(1, social.S_ACCEPT, dk(0))
check(r["ok"] == 1 and r["friends"][0]["name"] == "P0" and r["friends"][0]["status"] in ("menu", "launcher"), "TCP: accepted, friend online")
r = sreq(1, social.S_MSG, dk(0) + "\nzażółć gęślą jaźń")
check(r["ok"] == 1 and r["chat"]["msgs"][-1]["t"] == "zażółć gęślą jaźń", "TCP: private message (UTF-8)")
r = sreq(0, social.S_STATE)
check(r["unread"] == {dk(1): 1}, "TCP: the friend sees it unread")
r = sreq(0, social.S_CHAT, dk(1))
check(r["chat"]["msgs"][-1]["me"] is False and sreq(0, social.S_STATE)["unread"] == {}, "TCP: opening the chat reads it")
def quiet(payload):
    c = socket.create_connection(("127.0.0.1", port), timeout=0.6)
    c.sendall(struct.pack("<H", len(payload) + 1) + bytes([0xD8]) + payload)
    try:
        return c.recv(100)
    except socket.timeout:
        return b""
    finally:
        c.close()
check(quiet(DT[0].encode() + bytes([2, 0, 1])) == b"" and quiet(b"zz" * 32 + bytes([1, 0, 1])) == b"" and quiet(b"short") == b"", "TCP: wrong protocol version / bad token / short frame get no reply")
# the in-game notice poll carries the party / friend lines
sreq(0, social.S_ADD, "P2")
op, body = req(0xBA, DT[2].encode() + bytes([1, 0]))
check(op == 0xBB and b"|p|" in body and b"friend request" in body, "TCP: notice poll 0xBA carries the friend request as kind p: " + body.decode()[:80])
op, body = req(0xBA, DT[2].encode() + bytes([1, 1]))
check("zaproszenie" in body.decode("utf-8"), "... Polish for lang 1")

def reset():
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.last_arrival = 0
    PT.of.clear(); PT.inv.clear(); PT.leaders.clear(); PT.ready.clear()
def mkparty(idx):
    lead = DT[idx[0]]
    for i in idx[1:]:
        PT.invite_token(lead, DT[i]); PT.accept_token(DT[i], lead)
def fill(idx):
    now = time.time()
    for k, i in enumerate(idx):
        MM.queue[DT[i]] = now + k * 0.001; MM.seen[DT[i]] = now; MM.settle[DT[i]] = 0
    return MM.try_form()
def teams(pl):
    return {k: [p for j, p in enumerate(pl) if daemon.team_of(j) == k] for k in (0, 1)}
def pls():
    return [pl for pl in MM.matches.values()]

reset(); mkparty([0, 1, 2])
fill([4, 0, 5, 1, 6, 2, 7, 3])
pl = pls()[0]; tm = teams(pl)
check(len(MM.matches) == 1 and len(pl) == 8 and any({DT[0], DT[1], DT[2]} <= set(v) for v in tm.values()), "party of 3 + 5 singles: one match, party on one team")
reset(); mkparty([0, 1, 2, 3])
fill([0, 1, 2, 3, 4, 5, 6, 7])
tm = teams(pls()[0])
check(any({DT[0], DT[1], DT[2], DT[3]} <= set(v) for v in tm.values()) and len(tm[0]) == len(tm[1]) == 4, "party of 4 in a 4v4: one whole team")
reset(); mkparty([0, 1])
fill([0, 4])
check(not MM.matches and DT[0] in MM.queue, "leader + one single searching: the member is missing -> the party is held, nobody matched without it")
fill([1])
check(len(MM.matches) == 1 and set(pls()[0]) == {DT[0], DT[1], DT[4]}, "the missing member searches -> party + the single form 2 v 1: " + str([[DN[t] for t in v] for v in teams(pls()[0]).values()]))
tm = teams(pls()[0])
check(any({DT[0], DT[1]} <= set(v) for v in tm.values()), "... party together")
reset(); mkparty([0, 1])
fill([0, 1])
check(not MM.matches, "a lone party of 2 (no opponents) waits: it would be 2 v 0")
fill([4])
check(len(MM.matches) == 1, "an opponent arrives -> the match forms")
reset(); mkparty([0, 1, 2])
fill([0, 1, 2, 4])
check(not MM.matches, "party of 3 + 1 single would be a 3v1: held")
fill([5])
check(len(MM.matches) == 1 and len(pls()[0]) == 5, "a 2nd single arrives -> 3v2")
reset(); mkparty([0, 1, 2, 3])
fill([4, 5, 6, 7, 8, 0, 1, 2, 3])
pl = pls()[0]
check(len(MM.matches) == 1 and len(pl) == 5 and DT[0] not in pl and len(MM.queue) == 4, "party of 4 does not fit the 3 slots left after 5 singles: the singles play, the whole party waits in the queue")
reset(); mkparty([0, 1]); mkparty([2, 3])
fill([0, 2, 1, 3, 4, 5])
tm = teams(pls()[0])
check(len(MM.matches) == 1 and any({DT[0], DT[1]} <= set(v) for v in tm.values()) and any({DT[2], DT[3]} <= set(v) for v in tm.values()), "two parties of 2 + 2 singles: each whole")
reset(); mkparty([0, 1, 2])
PT.leave(DT[0])
check(PT.pid(DT[1]) is None and PT.pid(DT[2]) is None, "the leader leaves: the party is gone (no promote)")
fill([0, 1, 2])
check(len(MM.matches) == 1 and len(pls()[0]) == 3, "... and its former members queue as singles")
reset(); mkparty([0, 1, 2]); PT.promote(DT[0], DT[1]); PT.leave(DT[0])
fill([1, 2, 4, 5, 6])
check(len(MM.matches) == 1 and PT.pid(DT[1]) == PT.pid(DT[2]), "leader promoted a member, then left: the rest of the party queues together")
# labels on the searching page
reset(); mkparty([0, 1])
daemon._SF_CACHE["key"] = None
MM.queue[DT[0]] = time.time(); MM.seen[DT[0]] = time.time(); MM.queue[DT[4]] = time.time() + 0.1; MM.seen[DT[4]] = time.time()
fr = daemon.searching_frame(DT[4])
check(b"P0 [T" in fr and b"(party lead)" in fr, "searching page labels the party leader")
fr0 = daemon.searching_frame(DT[0])
check(b"P1 (party - not searching)" in fr0, "the leader sees the member who has not pressed FIND MATCH yet")
MM.queue.clear()
# the old op 0xDA keeps working
reset()
op, body = req(0xDA, DT[0].encode() + bytes([1]) + b"p1")
check(op == 0xDB and body.startswith(b"ok=1"), "legacy 0xDA invite by name still works: " + body.decode())
op, body = req(0xDA, DT[1].encode() + bytes([2]) + b"P0")
check(body.startswith(b"ok=1") and b"n=2" in body, "legacy 0xDA accept: " + body.decode())
reset()
# gc keeps launcher-only party members
reset(); mkparty([0, 1])
daemon.PRES.players.pop(DT[1], None)
SOC = daemon.SOCIAL; SOC.touch(DT[1])
daemon.gc_state(time.time(), ttl=3600)
check(PT.pid(DT[1]) is not None, "gc: a party member who is only in the launcher stays")

print("\n%d failure(s)" % len(FAILS))
for f in FAILS: print("  FAIL:", f)
sys.exit(1 if FAILS else 0)
