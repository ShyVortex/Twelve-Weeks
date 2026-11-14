"""Friends + parties (a friends and party system: pending requests, friends, online / offline, and parties that have a
leader and queue together as a team). Pure logic over an injected host, no sockets; tools/daemon.py wires it (op 0xD8 -> 0xD9) and the
launcher's FRIENDS page / the notice poll of t2r-ext read it.

Accounts: a player is "s:<steamid>" when the daemon knows the Steam account of the token, else "t:<hash of the install id>" (never a raw token or
token fragment: these ids go to other players). Friends are stored per account in the daemon's SQLite database (table social_friends: one row per pair,
state 0 = pending request a -> b, 1 = friends), so they follow the player to every install of one Steam account. A later-learned Steam id adopts the rows
of the token's old "t:" account.

Presence: a token is online while its game is present in the daemon's presence table (game_tokens) or its launcher polled the FRIENDS ops within
PRESENCE_TTL. Status codes (language-neutral, the launcher translates): match | search | menu (in the game's menu) | launcher | off.

Parties are in memory only (a party never outlives the daemon): leader + up to Parties.MAX - 1 members (a party must fit one team), invites by the leader to
friends only, accepted by the invitee. A leader that leaves disbands the party unless a member was promoted first; a leader that merely times out (offline) hands
it to the next member. The matchmaker keeps a party on one team and holds it until EVERY member searches (held_parties / pick_units below).

Wire (t2r-launcher, its own short TCP connection):
  launcher -> daemon  0xD8 [64B token][u8 ver=1][u8 lang 0 en / 1 pl][u8 sub][UTF-8 argument]
  daemon -> launcher  0xD9 UTF-8 JSON  {"ok":1|0,"err":"<code>","v":1,"me":..,"friends":[..],"in":[..],"out":[..],"party":{..}|null,"pinv":[..],"found":[..]}
In game the same events reach the player as notice-poll lines (kind p, op 0xBA/0xBB: notes_for).
"""
import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time

OP_REQ, OP_REPLY = 0xD8, 0xD9
S_STATE, S_SEARCH, S_ADD, S_ACCEPT, S_REMOVE, S_INVITE, S_JOIN, S_DECLINE, S_LEAVE, S_KICK, S_PROMOTE, S_READY = range(1, 13)
SUB_NAMES = {S_STATE: "state", S_SEARCH: "search", S_ADD: "add", S_ACCEPT: "accept", S_REMOVE: "remove", S_INVITE: "invite", S_JOIN: "join",
             S_DECLINE: "decline", S_LEAVE: "leave", S_KICK: "kick", S_PROMOTE: "promote", S_READY: "ready"}
WRITE_SUBS = frozenset((S_ADD, S_ACCEPT, S_REMOVE, S_INVITE, S_JOIN, S_DECLINE, S_LEAVE, S_KICK, S_PROMOTE, S_READY))
PRESENCE_TTL = 60.0            # a launcher / game seen this recently is online
SEEN_WRITE_S = 30.0            # last-seen rows are rewritten at most this often per account
INVITE_TTL = 300.0
FRIEND_MAX = 100
REQUEST_MAX = 30               # pending requests one account may have open (out) at once
OPS_PER_MIN = 40               # write ops per account per minute
NOTE_BASE = 1000000            # notice ids of party / friend lines (notices.py ids stay far below)
NOTE_KEEP_S = 30.0             # a note waits this long for the 6 s notice poll
SEARCH_MAX = 8
PARTY_GRACE = 45.0             # a party member that was in neither the game nor the launcher for this long leaves its party
RANK = {"match": 0, "search": 1, "menu": 2, "launcher": 3, "off": 4}

# in-game lines (kind p of the notice poll), English / Polish: {n} = a player name
NOTES = {
    "freq": ("{n} sent you a friend request. Open the FRIENDS page of the launcher.", "{n} wysyła ci zaproszenie do znajomych. Otwórz stronę ZNAJOMI w launcherze."),
    "facc": ("{n} accepted your friend request.", "{n} przyjmuje twoje zaproszenie do znajomych."),
    "pinv": ("PARTY: {n} invited you to a party. Open the FRIENDS page of the launcher to join.", "GRUPA: {n} zaprasza cię do grupy. Otwórz stronę ZNAJOMI w launcherze, aby dołączyć."),
    "pjoin": ("PARTY: {n} joined your party.", "GRUPA: {n} dołącza do grupy."),
    "pleft": ("PARTY: {n} left the party.", "GRUPA: {n} opuszcza grupę."),
    "pkick": ("PARTY: you were removed from the party.", "GRUPA: zostajesz usunięty z grupy."),
    "pdis": ("PARTY: the party was disbanded.", "GRUPA: grupa została rozwiązana."),
    "plead": ("PARTY: {n} is the party leader now.", "GRUPA: {n} jest teraz liderem grupy."),
    "pq": ("PARTY: leader {n} is searching. Press READY UP to join.", "GRUPA: lider {n} szuka meczu. Wciśnij GOTOWY, aby dołączyć."),
    "pqm": ("PARTY: {n} is searching. Press READY UP to join.", "GRUPA: {n} szuka meczu. Wciśnij GOTOWY, aby dołączyć."),
    "kicked": ("{n}", "{n}"),            # admin kick: the whole line (with the optional reason) is the subject
    "pwait": ("PARTY: waiting for {n} to search.", "GRUPA: czekamy, aż {n} zacznie szukać."),
    "pneed": ("PARTY: waiting for opponents - {n} more player(s) needed so that both teams are even.", "GRUPA: czekamy na przeciwników - brakuje graczy: {n}, aby drużyny były równe."),
}


# the same two lines for a game that has the in-game FRIENDS panel (t2r-ext sends flag byte 1 in the notice poll; invite notifications show when outside
# of the party menu): the panel opens with P
NOTES_INGAME = {
    "freq": ("{n} sent you a friend request. Press P to open FRIENDS.", "{n} wysyła ci zaproszenie do znajomych. Wciśnij P, aby otworzyć ZNAJOMYCH."),
    "pinv": ("PARTY: {n} invited you to a party. Press P to open FRIENDS and join.", "GRUPA: {n} zaprasza cię do grupy. Wciśnij P, aby otworzyć ZNAJOMYCH i dołączyć."),
}


def acct_hash(token_id):
    return "t:" + hashlib.sha256((token_id or "").encode("utf-8", "ignore")).hexdigest()[:16]


def _token_id(token):
    t = (token or "").lower()
    return t[40:64] if len(t) == 64 else t        # = clan.token_id (the install id inside a token)


# ---------------------------------------------------------------- parties
class Parties:
    """token -> party id (`of`), leader per party (`leaders`; a party without an entry is led by its first member: tests and the old op 0xDA fill `of`
    directly), invitations {invitee token: {inviter token: time}} (`inv`). Methods only change state and queue events (token, kind, subject token) for
    Social to turn into notes after the lock is released; nothing here calls out."""
    MAX = 4                                    # a party must fit one team (the daemon sets MATCH_SIZE // 2)

    def __init__(self, max_size=None, now=time.time, lookup=None):
        self.lock = threading.RLock()
        self.now = now
        self.lookup = lookup                   # name -> online token (the old by-name invite / accept)
        if max_size:
            self.MAX = max(1, int(max_size))
        self.of = {}
        self.inv = {}
        self.leaders = {}
        self.ready = set()
        self.events = []

    # --- reads
    def pid(self, token):
        with self.lock:
            return self.of.get(token)

    def members(self, token):
        with self.lock:
            pid = self.of.get(token)
            return [t for t, p in self.of.items() if p == pid] if pid else [token]

    def _mem(self, pid):
        return [t for t, p in self.of.items() if p == pid]

    def leader_of(self, pid):
        with self.lock:
            mem = self._mem(pid)
            l = self.leaders.get(pid)
            return l if l in mem else (mem[0] if mem else None)

    def leader(self, token):
        with self.lock:
            pid = self.of.get(token)
            return self.leader_of(pid) if pid else None

    def is_leader(self, token):
        return self.leader(token) == token

    def size(self, token):
        with self.lock:
            pid = self.of.get(token)
            return len(self._mem(pid)) if pid else 0

    def invites_for(self, token):
        """[(inviter token, age s)] of the live invitations to `token` (the inviter still leads / is not in another party)."""
        now = self.now()
        out = []
        with self.lock:
            for inviter, tm in self.inv.get(token, {}).items():
                if now - tm > INVITE_TTL:
                    continue
                pid = self.of.get(inviter)
                if pid and self.leader_of(pid) != inviter:
                    continue
                out.append((inviter, now - tm))
        return sorted(out, key=lambda x: x[1])

    # --- changes
    def _ev(self, to, kind, subject=None):
        self.events.append((to, kind, subject))

    def drain(self):
        with self.lock:
            ev, self.events = self.events, []
        return ev

    def invite_token(self, inviter, invitee):
        """None when the invitation was stored, else an error code."""
        with self.lock:
            if invitee == inviter:
                return "self"
            pid = self.of.get(inviter)
            if pid and self.leader_of(pid) != inviter:
                return "notleader"
            if pid and self.of.get(invitee) == pid:
                return "already"
            if pid and len(self._mem(pid)) >= self.MAX:
                return "full"
            self.inv.setdefault(invitee, {})[inviter] = self.now()
            self._ev(invitee, "pinv", inviter)
        return None

    def accept_token(self, invitee, inviter):
        """(party id, None) or (None, error code)."""
        with self.lock:
            tm = self.inv.get(invitee, {}).get(inviter)
            if tm is None or self.now() - tm > INVITE_TTL:
                return None, "expired"
            pid = self.of.get(inviter)
            if pid and self.leader_of(pid) != inviter:
                return None, "expired"                 # it does not lead that party any more
            if pid and self.of.get(invitee) == pid:
                self.inv.pop(invitee, None)
                return pid, None
            if pid and len(self._mem(pid)) >= self.MAX:
                return None, "full"
            if invitee in self.of:
                self._leave(invitee, "left")           # joining another party leaves the old one
            if not pid:
                pid = secrets.token_hex(3)
                self.of[inviter] = pid
                self.leaders[pid] = inviter
            for t in self._mem(pid):
                if t != invitee:
                    self._ev(t, "pjoin", invitee)
            self.of[invitee] = pid
            self.inv.pop(invitee, None)
            self.ready.add(invitee)                    # a member joins READY (the leader's FIND MATCH takes it along; UNREADY opts out)
            return pid, None

    def decline_token(self, invitee, inviter):
        with self.lock:
            d = self.inv.get(invitee)
            if d and inviter in d:
                del d[inviter]
                if not d:
                    del self.inv[invitee]
                return True
        return False

    def _leave(self, token, why):
        """Caller holds the lock. why: left (own wish) | kicked | timeout (gone offline)."""
        pid = self.of.get(token)
        if not pid:
            return None
        was_leader = self.leader_of(pid) == token
        del self.of[token]
        self.ready.discard(token)
        rest = self._mem(pid)
        if was_leader and why == "timeout" and len(rest) >= 2:
            self.leaders[pid] = rest[0]
            for t in rest:
                self._ev(t, "plead", rest[0])
        elif was_leader:
            for t in rest:                              # the leader leaves: the party is over (promote first to keep it)
                del self.of[t]
                self.ready.discard(t)
                self._ev(t, "pdis", token)
            self.leaders.pop(pid, None)
            return pid
        else:
            for t in rest:
                self._ev(t, "pleft", token)
        if why == "kicked":
            self._ev(token, "pkick", None)
        if len(rest) < 2:                               # a party of one is no party
            for t in rest:
                del self.of[t]
                self.ready.discard(t)
                self._ev(t, "pdis", token)
            self.leaders.pop(pid, None)
        return pid

    def leave(self, token):
        """The player leaves its party (a leader disbands it) and its invitations (given and received) are void. True when it was in one."""
        with self.lock:
            had = token in self.of
            self._leave(token, "left")
            self.inv.pop(token, None)
            for invitee in list(self.inv):
                self.inv[invitee].pop(token, None)
                if not self.inv[invitee]:
                    del self.inv[invitee]
        return had

    def kick(self, leader, target):
        with self.lock:
            pid = self.of.get(leader)
            if not pid or self.leader_of(pid) != leader:
                return "notleader"
            if target == leader or self.of.get(target) != pid:
                return "notmember"
            self._leave(target, "kicked")
        return None

    def promote(self, leader, target):
        with self.lock:
            pid = self.of.get(leader)
            if not pid or self.leader_of(pid) != leader:
                return "notleader"
            if target == leader or self.of.get(target) != pid:
                return "notmember"
            self.leaders[pid] = target
            for t in self._mem(pid):
                self._ev(t, "plead", target)
        return None

    def clear_ready(self, tokens):
        """A match formed: its players start the next party round unready."""
        with self.lock:
            for t in tokens:
                self.ready.discard(t)

    def set_ready(self, token, on):
        with self.lock:
            if token not in self.of:
                return "noparty"
            (self.ready.add if on else self.ready.discard)(token)
        return None

    def gc(self, keep, now=None):
        """Drop members that are gone (not in `keep`: a leader hands the party to the next member) and invitations older than their life. Returns the number dropped."""
        now = self.now() if now is None else now
        n = 0
        with self.lock:
            for t in [t for t in list(self.of) if t not in keep]:
                if t in self.of:
                    self._leave(t, "timeout")
                n += 1
            for pid in [p for p in list(self.leaders) if p not in self.of.values()]:
                del self.leaders[pid]
            for invitee in list(self.inv):
                d = self.inv[invitee]
                for inviter in [i for i, tm in d.items() if now - tm > INVITE_TTL or i not in keep]:
                    del d[inviter]
                    n += 1
                if not d or invitee not in keep:
                    self.inv.pop(invitee, None)
        return n

    # --- the old op 0xDA (by display name, online players only)
    def invite(self, token, name):
        other = self.lookup(name) if self.lookup else None
        return bool(other) and self.invite_token(token, other) is None

    def accept(self, token, name):
        inviter = self.lookup(name) if self.lookup else None
        return bool(inviter) and self.accept_token(token, inviter)[1] is None

    def text(self, token, name_of=lambda t: "PLAYER"):
        pid = self.pid(token)
        mem = self.members(token) if pid else []
        inv = [t for t, _ in self.invites_for(token)]
        return "n=%d m=%s inv=%s" % (len(mem), ",".join((name_of(t) or "PLAYER").replace(" ", "_") for t in mem) or "-",
                                     ",".join((name_of(t) or "PLAYER").replace(" ", "_") for t in inv) or "-")


# ---------------------------------------------------------------- matchmaking helpers (pure)
def held_parties(ready, parties):
    """(tokens of `ready` whose party is whole, {party id: [members not ready]}): a party queues as one unit, so its members are matchable only
    when every one of them is ready (searching right now). Solo players always pass."""
    rs = set(ready)
    ok, held, bad = [], {}, set()
    for t in ready:
        pid = parties.pid(t)
        if pid and len(parties.members(t)) > 1:
            miss = [m for m in parties.members(t) if m not in rs]
            if miss:
                held[pid] = miss
                bad.add(t)
    for t in ready:
        if t not in bad:
            ok.append(t)
    return ok, held


def units_of(ready, parties):
    """The queue-ordered units: a party is one unit (at the place of its first member), anybody else a unit of one."""
    units, at = [], {}
    for t in ready:
        pid = parties.pid(t) if len(parties.members(t)) > 1 else None
        if pid is None:
            units.append([t])
        elif pid in at:
            at[pid].append(t)
        else:
            at[pid] = [t]
            units.append(at[pid])
    return units


def party_need(p):
    """Players a match needs so that a party of p stays on one team with the other team not smaller than p - 1 (teams differ by at most 1)."""
    return 1 if p <= 1 else 2 * p - 1


def party_shortfall(ready, parties, size, chosen=()):
    """{party id: (members, missing)} of the ready parties that are NOT in `chosen` because too few players are searching (missing = players still
    needed in the whole lobby, > 0). A party that is left out only because the lobby is full has missing 0 and is not listed."""
    out, cs = {}, set(chosen)
    for u in units_of(ready, parties):
        if len(u) > 1 and not (set(u) & cs):
            miss = party_need(len(u)) - len(ready)
            if miss > 0 and len(u) <= max(1, size // 2):
                out[parties.pid(u[0])] = (u, miss)
    return out


def pick_units(ready, parties, size):
    """The players of the next match from the ready (queue-ordered, parties whole) tokens: whole units up to `size`, a party that does not fit the
    open slots waits, and a party of p needs at least 2p - 1 players in the match so that it stays on one team with the other team not smaller than
    p - 1 (a party of 3 beside one single would be split or play 3 v 1)."""
    units = [u for u in units_of(ready, parties) if len(u) <= max(1, size // 2) or len(u) == 1]
    chosen, total = [], 0
    for u in units:
        if total + len(u) <= size:
            chosen.append(u)
            total += len(u)
    dropped = []
    while True:
        bad = [u for u in chosen if len(u) > 1 and total < 2 * len(u) - 1]
        if not bad:
            break
        u = max(bad, key=len)
        chosen.remove(u)
        dropped.append(u)
        total -= len(u)
        for v in units:                                 # a smaller unit that did not fit before may fit now
            if v not in chosen and v not in dropped and total + len(v) <= size:
                chosen.append(v)
                total += len(v)
    order = {t: i for i, t in enumerate(ready)}
    chosen.sort(key=lambda u: order.get(u[0], 0))
    return [t for u in chosen for t in u]


# ---------------------------------------------------------------- friends + presence
class Social:
    """host: now() | db() (context manager -> sqlite connection) | steamid(token) | name(token) | game_tokens() | alive_tokens() (game + queued + in a match) |
    mm_state(token) -> match/search/None | log(*a).
    db() must NOT hold the daemon's database lock (steamid / name take it, and it is not re-entrant): every write below is committed at once, so no write
    transaction is open while a host function runs."""

    def __init__(self, host, parties):
        self.h = host
        self.p = parties
        self.lock = threading.RLock()
        self.hb = {}                   # token -> last launcher poll
        self.notes = {}                # token -> [(id, kind, subject name, until)]
        self.nlock = threading.Lock()
        self.seq = NOTE_BASE
        self.seen_w = {}               # account -> time of its last last-seen row write
        self.rate = {}                 # account -> [times of write ops]
        self.qnote = {}                # party id -> time of the last "leader searches" note
        self._om = (0.0, {}, set())
        self._tick_at = 0.0
        self._pt_at = 0.0
        self.gone = {}                 # party token -> time it was first seen neither in the game nor in the launcher

    # --- accounts + presence
    def acct(self, token):
        sid = self.h.steamid(token)
        return ("s:%d" % sid) if sid else acct_hash(_token_id(token))

    def online_map(self):
        """({account: [tokens]}, game token set), cached ~1 s."""
        now = self.h.now()
        at, m, g = self._om
        if now - at < 1.0:
            return m, g
        g = set(self.h.game_tokens())
        toks = g | {t for t, tm in self.hb.items() if now - tm < PRESENCE_TTL}
        m = {}
        for t in toks:
            m.setdefault(self.acct(t), []).append(t)
        self._om = (now, m, g)
        return m, g

    def status_of(self, key, om=None):
        m, g = om or self.online_map()
        toks = m.get(key)
        if not toks:
            return "off"
        best = "launcher"
        for t in toks:
            s = self.h.mm_state(t)
            if s == "match":
                return "match"
            if s == "search":
                best = "search"
            elif best == "launcher" and t in g:
                best = "menu"
        return best

    def token_for(self, key):
        """The online token of an account that was active last (game first)."""
        m, g = self.online_map()
        toks = m.get(key) or []
        if not toks:
            return None
        return sorted(toks, key=lambda t: (t in g, self.hb.get(t, 0)), reverse=True)[0]

    def touch(self, token):
        self.hb[token] = self.h.now()

    def launcher_tokens(self):
        now = self.h.now()
        return {t for t, tm in self.hb.items() if now - tm < PRESENCE_TTL}

    # --- storage
    def _ensure(self, c):
        c.execute("CREATE TABLE IF NOT EXISTS social_friends(a TEXT, b TEXT, state INT, since REAL, PRIMARY KEY(a, b))")
        c.execute("CREATE INDEX IF NOT EXISTS social_friends_b ON social_friends(b)")
        c.execute("CREATE TABLE IF NOT EXISTS social_seen(acct TEXT PRIMARY KEY, name TEXT, last REAL)")

    def _adopt(self, c, token, key):
        """The token's Steam id became known: the rows of its old install account move to the Steam account (only when there are some)."""
        old = acct_hash(_token_id(token))
        if key == old:
            return
        try:
            for col, other in (("a", "b"), ("b", "a")):
                for row in c.execute("SELECT %s, state, since FROM social_friends WHERE %s=?" % (other, col), (old,)).fetchall():
                    if row[0] != key:
                        c.execute("INSERT OR IGNORE INTO social_friends(%s,%s,state,since) VALUES(?,?,?,?)" % (col, other), (key, row[0], row[1], row[2]))
                c.execute("DELETE FROM social_friends WHERE %s=?" % col, (old,))
            r = c.execute("SELECT name, last FROM social_seen WHERE acct=?", (old,)).fetchone()
            if r:
                c.execute("INSERT OR IGNORE INTO social_seen(acct,name,last) VALUES(?,?,?)", (key, r[0], r[1]))
                c.execute("DELETE FROM social_seen WHERE acct=?", (old,))
            c.commit()
        except sqlite3.Error as ex:
            self.h.log("SOCIAL adopt failed", repr(ex))

    def _seen(self, c, key, name, now, force=False):
        if not force and now - self.seen_w.get(key, 0) < SEEN_WRITE_S:
            return
        self.seen_w[key] = now
        c.execute("INSERT INTO social_seen(acct,name,last) VALUES(?,?,?) ON CONFLICT(acct) DO UPDATE SET name=excluded.name,last=excluded.last", (key, name, now))
        c.commit()

    def name_of(self, c, key, om=None):
        m, _ = om or self.online_map()
        for t in m.get(key) or ():
            n = self.h.name(t)
            if n:
                return n
        r = c.execute("SELECT name FROM social_seen WHERE acct=?", (key,)).fetchone()
        if r and r[0]:
            return r[0]
        if key.startswith("s:"):
            r = c.execute("SELECT name FROM players WHERE steamid=? AND name IS NOT NULL AND name<>'' ORDER BY last_seen DESC LIMIT 1", (int(key[2:]),)).fetchone()
            if r and r[0]:
                return r[0]
        return "PLAYER"

    def tick(self, now=None):
        """About every SEEN_WRITE_S: write last-seen rows of everybody online (a game-only player has no launcher poll that would), and drop dead launcher polls."""
        now = self.h.now() if now is None else now
        self.party_tick(now)
        if now - self._tick_at < SEEN_WRITE_S:
            return 0
        self._tick_at = now
        for t in [t for t, tm in self.hb.items() if now - tm > 10 * PRESENCE_TTL]:
            del self.hb[t]
        m, _ = self.online_map()
        n = 0
        rows = [(key, next((self.h.name(t) for t in toks if self.h.name(t)), "PLAYER")) for key, toks in m.items()]
        try:
            with self.h.db() as c:
                self._ensure(c)
                for key, name in rows:
                    self._seen(c, key, name, now)
                    n += 1
        except sqlite3.Error as ex:
            self.h.log("SOCIAL tick failed", repr(ex))
        return n

    def party_tick(self, now=None):
        """About every 10 s: party members (and invitees) that were in neither the game nor the launcher for PARTY_GRACE s are removed - a leader that went
        offline hands the party to the next member, so a member who searches is never held for a leader that is gone. Returns the number removed."""
        now = self.h.now() if now is None else now
        if now - self._pt_at < 10.0:
            return 0
        self._pt_at = now
        alive = set(self.h.alive_tokens()) | self.launcher_tokens()
        with self.p.lock:
            tracked = set(self.p.of) | set(self.p.inv) | {i for d in self.p.inv.values() for i in d}
        out = set()
        for t in tracked:
            if t in alive:
                self.gone.pop(t, None)
            elif now - self.gone.setdefault(t, now) >= PARTY_GRACE:
                out.add(t)
        for t in [t for t in self.gone if t not in tracked]:
            del self.gone[t]
        n = self.p.gc(alive | (tracked - out), now) if tracked else 0
        for t in out:
            self.gone.pop(t, None)
        self._drain()
        return n

    # --- notes (in-game lines)
    def note(self, token, kind, subject_name=""):
        if not token or kind not in NOTES:
            return
        with self.nlock:
            self.seq += 1
            lst = self.notes.setdefault(token, [])
            lst.append((self.seq, kind, subject_name or "", self.h.now() + NOTE_KEEP_S))
            del lst[:-6]

    def note_acct(self, key, kind, subject_name=""):
        m, _ = self.online_map()
        for t in m.get(key) or ():
            self.note(t, kind, subject_name)

    def notes_for(self, token, lang=0, ingame=False):
        """[(id, 'p', seconds on screen, text)] for the notice poll of this token's game (each stays NOTE_KEEP_S; the ext shows every id once)."""
        now = self.h.now()
        with self.nlock:
            lst = [x for x in self.notes.get(token, ()) if x[3] > now]
            if lst:
                self.notes[token] = lst
            else:
                self.notes.pop(token, None)
        out = []
        for nid, kind, who, _ in lst[-2:]:
            txt = (NOTES_INGAME.get(kind) if ingame else None) or NOTES[kind]
            txt = txt[1 if lang == 1 else 0].replace("{n}", who)
            out.append((nid, "p", 8, txt))
        return out

    def _drain(self):
        """Party events -> notes (called after every party change, outside the parties' lock)."""
        for to, kind, subj in self.p.drain():
            self.note(to, kind, (self.h.name(subj) or "PLAYER") if subj else "")

    # --- queue hooks (daemon)
    def on_queue(self, token, queued):
        """`token` pressed FIND MATCH. A party member tells the others: the leader's search asks the members to follow, a member's search tells the leader.
        `queued` = predicate token -> bool (already searching)."""
        if not self.p.pid(token) or len(self.p.members(token)) < 2:
            return 0
        pid = self.p.pid(token)
        now = self.h.now()
        if now - self.qnote.get((pid, token), 0) < 20.0:
            return 0
        self.qnote[(pid, token)] = now
        if len(self.qnote) > 200:
            self.qnote.clear()
        n = 0
        who = self.h.name(token) or "PLAYER"
        lead = self.p.leader(token)
        if token != lead:
            return 0                       # (only the leader searches; a member's READY UP is not a search)
        for m in self.p.members(token):
            if m == token or queued(m) or m in self.p.ready:
                continue                   # ready members follow the leader by themselves (their client starts the search)
            self.note(m, "pq" if token == lead else "pqm", who)
            n += 1
        return n

    def search_gate(self, token, queued):
        """Party rule (members only READY UP, the leader searches). True = this FIND MATCH request must NOT queue `token`:
        - a non-leader member whose leader is not searching: the press is a READY UP / UNREADY toggle (the client sends it as a ready op);
          a member whose leader searches is let in (his client starts that search by itself once he is ready);
        - the leader while a mate is neither ready nor searching (the client holds the press back and says who).
        A solo player is never held. `queued` = predicate token -> bool (already searching)."""
        if not self.p.pid(token) or len(self.p.members(token)) < 2:
            return False
        lead = self.p.leader(token)
        if token == lead:
            return False      # the leader is never held - its search waits for the members (daemon PARTY-WAIT), ready ones follow by themselves
        return not (lead and queued(lead))

    def party_rows(self, token):
        """[(token, name, leader?)] of the token's party mates that are NOT searching (the searching page lists them as waiting)."""
        if not self.p.pid(token):
            return []
        lead = self.p.leader(token)
        return [(m, self.h.name(m) or "PLAYER", m == lead) for m in self.p.members(token) if m != token]

    # --- ops
    def _limited(self, key):
        now = self.h.now()
        l = [t for t in self.rate.get(key, ()) if now - t < 60.0]
        l.append(now)
        self.rate[key] = l
        if len(self.rate) > 2000:
            self.rate = {k: v for k, v in self.rate.items() if v and now - v[-1] < 60.0}
        return len(l) > OPS_PER_MIN

    def handle(self, token, lang, sub, arg=""):
        """One launcher request -> the reply dict (always a fresh state plus ok / err)."""
        res = {"ok": 1, "err": ""}
        try:
            with self.h.db() as c:
                self._ensure(c)
                me = self.acct(token)
                self._adopt_once(c, token, me)
                self.touch(token)
                om = self.online_map()
                if token not in om[0].get(me, ()):
                    self._om = (0.0, {}, set())      # (the launcher's own first poll: recount so that it is online in this very reply)
                    om = self.online_map()
                self._seen(c, me, self.h.name(token) or token_name_fallback(token), self.h.now())
                err = None
                if sub in WRITE_SUBS and self._limited(me):
                    err = "rate"
                elif sub == S_SEARCH:
                    res["found"] = self._search(c, me, arg, om)
                elif sub == S_ADD:
                    err = self._add(c, token, me, arg, om)
                elif sub == S_ACCEPT:
                    err = self._accept(c, token, me, arg, om)
                elif sub == S_REMOVE:
                    err = self._remove(c, me, arg)
                elif sub in (S_INVITE, S_JOIN, S_DECLINE, S_KICK, S_PROMOTE):
                    err = self._party_op(c, token, me, sub, arg, om)
                elif sub == S_LEAVE:
                    self.p.leave(token)
                elif sub == S_READY:
                    err = self.p.set_ready(token, arg.strip() != "0")
                elif sub != S_STATE:
                    err = "bad"
                self._drain()
                if err:
                    res["ok"], res["err"] = 0, err
                res.update(self._state(c, token, me, lang))
        except sqlite3.Error as ex:
            self.h.log("SOCIAL db error", repr(ex))
            res = {"ok": 0, "err": "db"}
        return res

    def _adopt_once(self, c, token, key):
        if key.startswith("s:") and self.seen_w.get(("adopt", token)) is None:
            self.seen_w[("adopt", token)] = 1
            self._adopt(c, token, key)

    def _rel(self, c, a, b):
        """None | 'friend' | 'out' (a asked b) | 'in' (b asked a)."""
        r = c.execute("SELECT a, state FROM social_friends WHERE (a=? AND b=?) OR (a=? AND b=?)", (a, b, b, a)).fetchone()
        if not r:
            return None
        return "friend" if r[1] == 1 else ("out" if r[0] == a else "in")

    def _resolve(self, c, text, om):
        """A friend target typed or clicked: an account id ("s:..." / "t:..."), a 17 digit Steam id or an exact player name -> (account, error)."""
        text = (text or "").strip()
        if re.fullmatch(r"[st]:[0-9a-f]{1,20}", text):
            if text.startswith("s:"):
                if not c.execute("SELECT 1 FROM players WHERE steamid=? LIMIT 1", (int(text[2:]) if text[2:].isdigit() else -1,)).fetchone() and text not in om[0]:
                    return None, "unknown"
            elif not c.execute("SELECT 1 FROM social_seen WHERE acct=?", (text,)).fetchone() and text not in om[0]:
                return None, "unknown"
            return text, None
        if re.fullmatch(r"\d{15,20}", text):
            key = "s:" + text
            if not c.execute("SELECT 1 FROM players WHERE steamid=? LIMIT 1", (int(text),)).fetchone() and key not in om[0]:
                return None, "unknown"
            return key, None
        found = self._search(c, "", text, om, exact=True)
        if len(found) == 1:
            return found[0]["id"], None
        return None, "unknown" if not found else "ambiguous"

    def _search(self, c, me, text, om, exact=False):
        text = (text or "").strip()[:31]
        if len(text) < 2:
            return []
        low = text.lower()
        like = low.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        hits = {}
        def add(key, name):
            if key and key != me and key not in hits and name:
                hits[key] = name
        if re.fullmatch(r"\d{15,20}", text):
            key = "s:" + text
            r = c.execute("SELECT name FROM players WHERE steamid=? AND name<>'' ORDER BY last_seen DESC LIMIT 1", (int(text),)).fetchone()
            if r or key in om[0]:
                add(key, r[0] if r else self.name_of(c, key, om))
        else:
            for t in sum(om[0].values(), []):                  # online players first (their shown name incl. clan tag)
                n = self.h.name(t) or ""
                if n.lower() == low or (not exact and n.lower().startswith(low)):
                    add(self.acct(t), n)
            for tid, n, tg in c.execute("SELECT token_id, name, tag FROM names WHERE lower(name)" + (" = ?" if exact else " LIKE ? ESCAPE '\\'") + " LIMIT 40",
                                        (low if exact else like + "%",)):
                key = tid if str(tid).startswith("s:") else acct_hash(tid)
                add(key, ("[%s] %s" % (tg, n)) if tg else n)
            for sid, n in c.execute("SELECT steamid, name FROM players WHERE steamid>0 AND lower(name)" + (" = ?" if exact else " LIKE ? ESCAPE '\\'") +
                                    " ORDER BY last_seen DESC LIMIT 40", (low if exact else like + "%",)):
                add("s:%d" % sid, n)
            for key, n in c.execute("SELECT acct, name FROM social_seen WHERE lower(name)" + (" = ?" if exact else " LIKE ? ESCAPE '\\'") + " LIMIT 40",
                                    (low if exact else like + "%",)):
                add(key, n)
        out = []
        for key, name in list(hits.items())[:SEARCH_MAX]:
            rel = (self._rel(c, me, key) if me else None) or ""
            out.append({"id": key, "name": name, "status": self.status_of(key, om) if rel == "friend" else "", "rel": rel})      # (presence is for friends only)
        return out

    def _count(self, c, key, where):
        return c.execute("SELECT COUNT(*) FROM social_friends WHERE " + where, (key,)).fetchone()[0]

    def _add(self, c, token, me, arg, om):
        key, err = self._resolve(c, arg, om)
        if err:
            return err
        if key == me:
            return "self"
        rel = self._rel(c, me, key)
        if rel == "friend":
            return "already"
        if rel == "out":
            return "pending"
        now = self.h.now()
        if rel == "in":                                         # they asked me already: asking back is accepting
            return self._accept(c, token, me, key, om)
        if c.execute("SELECT COUNT(*) FROM social_friends WHERE (a=? OR b=?) AND state=1", (me, me)).fetchone()[0] >= FRIEND_MAX:
            return "limit"
        if self._count(c, me, "a=? AND state=0") >= REQUEST_MAX:
            return "limit"
        c.execute("INSERT OR REPLACE INTO social_friends(a,b,state,since) VALUES(?,?,0,?)", (me, key, now))
        c.commit()
        self.note_acct(key, "freq", self.h.name(token) or "PLAYER")
        self.h.log("SOCIAL request", self.acct(token)[:12], "->", key[:14])
        return None

    def _accept(self, c, token, me, arg, om):
        key, err = self._resolve(c, arg, om)
        if err:
            return err
        r = c.execute("SELECT 1 FROM social_friends WHERE a=? AND b=? AND state=0", (key, me)).fetchone()
        if not r:
            return "expired"
        if c.execute("SELECT COUNT(*) FROM social_friends WHERE (a=? OR b=?) AND state=1", (me, me)).fetchone()[0] >= FRIEND_MAX:
            return "limit"
        c.execute("UPDATE social_friends SET state=1, since=? WHERE a=? AND b=?", (self.h.now(), key, me))
        c.commit()
        self.note_acct(key, "facc", self.h.name(token) or "PLAYER")
        return None

    def _remove(self, c, me, arg):
        key = (arg or "").strip()
        if not re.fullmatch(r"[st]:[0-9a-f]{1,20}", key):
            return "bad"
        c.execute("DELETE FROM social_friends WHERE (a=? AND b=?) OR (a=? AND b=?)", (me, key, key, me))
        c.commit()
        return None

    def _party_op(self, c, token, me, sub, arg, om):
        key = (arg or "").strip()
        if sub == S_INVITE:
            if self._rel(c, me, key) != "friend":
                return "notfriend"
            t = self.token_for(key)
            if not t:
                return "offline"
            return self.p.invite_token(token, t)
        if sub == S_JOIN or sub == S_DECLINE:
            inviter = next((i for i, _ in self.p.invites_for(token) if self.acct(i) == key), None)
            if not inviter:
                return "expired"
            if sub == S_DECLINE:
                self.p.decline_token(token, inviter)
                return None
            pid, err = self.p.accept_token(token, inviter)
            return err
        target = next((m for m in self.p.members(token) if m != token and self.acct(m) == key), None) if self.p.pid(token) else None
        if not target:
            return "notmember" if self.p.pid(token) else "noparty"
        return self.p.kick(token, target) if sub == S_KICK else self.p.promote(token, target)

    # --- the reply state
    def _state(self, c, token, me, lang):
        om = self.online_map()
        now = self.h.now()
        friends, inc, out = [], [], []
        mates = {self.acct(t): t for t in self.p.members(token)} if self.p.pid(token) else {}
        for a, b, st, since in c.execute("SELECT a, b, state, since FROM social_friends WHERE a=? OR b=?", (me, me)).fetchall():
            other = b if a == me else a
            name = self.name_of(c, other, om)
            if st == 1:
                status = self.status_of(other, om)
                r = c.execute("SELECT last FROM social_seen WHERE acct=?", (other,)).fetchone()
                friends.append({"id": other, "name": name, "status": status, "seen": None if status != "off" else (int(now - r[0]) if r and r[0] else None),
                                "party": other in mates and other != me, "since": int(since or 0)})
            elif a == me:
                out.append({"id": other, "name": name, "age": int(now - (since or now))})
            else:
                inc.append({"id": other, "name": name, "age": int(now - (since or now))})
        friends.sort(key=lambda f: (RANK[f["status"]], f["name"].lower()))
        inc.sort(key=lambda f: f["age"])
        out.sort(key=lambda f: f["age"])
        party = None
        pid = self.p.pid(token)
        if pid and len(self.p.members(token)) >= 1:
            lead = self.p.leader(token)
            mem = []
            for t in self.p.members(token):
                k = self.acct(t)
                mem.append({"id": k, "name": self.h.name(t) or "PLAYER", "status": self.status_of(k, om), "leader": t == lead,
                            "ready": (t == lead) or (t in self.p.ready) or self.h.mm_state(t) == "search", "me": t == token})
            mem.sort(key=lambda x: (not x["leader"], not x["me"], x["name"].lower()))
            party = {"id": pid, "leader": self.acct(lead) if lead else "", "meLeader": lead == token, "max": self.p.MAX, "members": mem,
                     "searching": any(self.h.mm_state(t) == "search" for t in self.p.members(token)),
                     "lsearch": bool(lead) and self.h.mm_state(lead) == "search"}
        pinv = []
        for inviter, age in self.p.invites_for(token):
            pinv.append({"id": self.acct(inviter), "name": self.h.name(inviter) or "PLAYER", "age": int(age)})
        return {"v": 1, "me": {"id": me, "name": self.h.name(token) or token_name_fallback(token)}, "friends": friends, "in": inc, "out": out,
                "party": party, "pinv": pinv, "max": self.p.MAX}


def token_name_fallback(token):
    """The name inside a T2N token (the launcher's tokens carry it), else PLAYER."""
    try:
        raw = bytes.fromhex(token)
        if raw.startswith(b"T2N:"):
            return raw[4:].split(b"\0")[0].decode("utf-8", "ignore")[:15] or "PLAYER"
    except (ValueError, TypeError):
        pass
    return "PLAYER"


def reply_json(d):
    return json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
