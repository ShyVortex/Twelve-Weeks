"""Private matches (spec, re/private-lobby-1117.md): a lobby with an owner, a join code, per-match rule overrides, a chosen map or a
private map pool, and NO clan / stats effects. Pure logic, no sockets; tools/daemon.py wires it (op 0xF8 -> 0xF9) into the matchmaker, the map
choice, the clan / stats / anti-AFK paths and the in-match rule reply the ext polls.

Wire (t2r-ext short connection, like the mode queue op 0xBC):
  ext -> daemon  0xF8 [64B token][u8 ver=1][u8 sub][ASCII argument]
  daemon -> ext  0xF9 ASCII "key=value key=value ..." (one line, spaces never inside a value: names use '_' for ' ')

Subs:
  1 STATE    -                    the caller's lobby (or in=0)
  2 CREATE   -                    a new lobby owned by the caller (it leaves any other lobby first); the owner's own lobby is returned again
  3 JOIN     <code>               join the lobby with that code (case-insensitive, 0 / O and 1 / I are read as O and I are not in the alphabet)
  4 LEAVE    -                    leave; the owner leaving hands the lobby to the oldest member, the last one out closes it
  5 SET      <key>=<int>          owner only: a rule, "map" (-1 vote, -2 random, else a map index) or "pool" (hex bit mask of map indices)
  6 TEAM     <member>=<team>      owner (teams rule HOST ASSIGNS) or the member itself (PLAYERS PICK): team 0 / 1, 255 = automatic
  7 KICK     <member>             owner only: member index (0 = the owner, refused)
  8 START    -                    owner only: the lobby goes to "launching"; every member's ext sees go=<n> and starts the search
  9 RULES    -                    in a match: pm=1 + the rules of the caller's private match (pm=0 for a public match)
  10 CANCEL  -                    owner only: back from "launching" to the lobby (nobody searches any more)

Reply keys: ok (1 / 0) err (code) in (1 in a lobby) code own (1 = caller owns it) me (caller's member index) st (0 lobby, 1 launching,
2 in a match) go (launch counter: a client starts its search when it changes) n (members) p<k> (name) t<k> (team 0 / 1 / 255 auto) h<k>
(1 = owner) map pool (hex) and every rule as <key>=<int>. RULES adds pm=1 / mid.
"""
import secrets
import threading
import time

OP_REQ, OP_REPLY = 0xF8, 0xF9
VER = 1
S_STATE, S_CREATE, S_JOIN, S_LEAVE, S_SET, S_TEAM, S_KICK, S_START, S_RULES, S_CANCEL = range(1, 11)
SUB_NAMES = {S_STATE: "state", S_CREATE: "create", S_JOIN: "join", S_LEAVE: "leave", S_SET: "set", S_TEAM: "team", S_KICK: "kick",
             S_START: "start", S_RULES: "rules", S_CANCEL: "cancel"}

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0 / O / 1 / I: read aloud and typed on a pad without mix-ups
CODE_LEN = 5
MAX_MEMBERS = 8                 # the engine holds 8 (daemon MATCH_SIZE)
MEMBER_TTL = 30.0               # a member whose ext has not polled for this long leaves (the menu polls every ~1.5 s)
LAUNCH_WAIT_S = 25.0            # after START: the match forms when every member searches, or after this long with the ones that do
LOBBY_IDLE_S = 3600.0           # an untouched lobby with nobody polling is gone after this (the TTL above normally empties it first)
AUTO = 255

# Rule table: key -> (default, allowed values in UI order, short English label). The ext keeps the same table (tools/ext/privlobby.c PR[]);
# the doc (re/private-lobby-1117.md) lists what each value does in game. Values are ints on the wire.
RULES = {
    # GAME RULES tab
    "parts": (100, (50, 100, 150, 200, 300, 500), "PARTS EARNED"),            # % of every parts award
    "lives": (20, (5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 0), "TEAM LIVES"),  # Supply Raid reinforcements per team; 0 = unlimited; 20 = 2013 (daemon LIVES_START)
    "invuln": (0, (0, 1), "INVINCIBILITY"),                                   # 1 = nobody takes damage (every hit on a player is dropped on the victim's side)
    "dmg": (0, (0, 1), "DAMAGE MODEL"),                                        # 0 FACTIONS (2013 table), 1 TLOU2 (engine damage, any headshot = would-kill hit)
    "downed": (1, (1, 0), "DOWNED SYSTEM"),                                    # 0 = no downed state: a would-kill hit kills at once
    "resp": (0, (0, 3, 5, 10, 15), "RESPAWN TIMER"),                           # 0 = 2013-style waves (5 - 15 s), else a fixed wait in s
    "craft": (0, (0, 1), "FREE CRAFTING"),                                     # 1 = crafting ingredients kept topped up
    "ff": (0, (0, 1), "FRIENDLY FIRE"),
    "radar": (1, (1, 0), "RADAR"),                                             # 0 = the HUD radar is hidden for everybody
    "glim": (1, (1, 0), "GUN LIMITS"),                                         # 0 = no per-team gun limits (daemon gunlimit)
    # MATCH tab
    "mode": (0, (0, 1), "MODE"),                                               # row of tools/modes.json: 0 SUPPLY RAID, 1 INTERROGATION
    "time": (0, (0, 5, 10, 15, 20, 30), "MATCH TIME"),                         # minutes, 0 = the mode's default clock (Supply Raid only)
    "teams": (0, (0, 1, 2), "TEAMS"),                                          # 0 BALANCED, 1 HOST ASSIGNS, 2 PLAYERS PICK
    "late": (1, (1, 0), "LATE JOIN"),                                          # lobby members may join the running match
    "maxp": (8, (2, 3, 4, 5, 6, 7, 8), "MAX PLAYERS"),
    "afk": (0, (0, 1), "AFK REMOVAL"),
    "ping": (0, (0, 1), "PING LIMIT"),
}
RULE_TABS = (("GAME RULES", ("parts", "lives", "invuln", "dmg", "downed", "resp", "craft", "ff", "radar", "glim")),
             ("MATCH", ("mode", "time", "teams", "late", "maxp", "afk", "ping")))
MAP_VOTE, MAP_RANDOM = -1, -2


def defaults():
    return {k: v[0] for k, v in RULES.items()}


def valid(key, value):
    r = RULES.get(key)
    return r is not None and isinstance(value, int) and value in r[1]


def clean_name(s):
    s = "".join(ch if (ch.isalnum() or ch in "-._") else "_" for ch in (s or ""))
    return s[:20] or "PLAYER"


def norm_code(s):
    s = "".join(ch for ch in (s or "").upper() if ch.isalnum())
    return s.replace("0", "O").replace("1", "I")[:CODE_LEN]


class Lobby:
    def __init__(self, code, owner, now, nmaps):
        self.code = code
        self.owner = owner
        self.members = [owner]          # join order; the owner is moved to the front
        self.team = {}                  # token -> 0 / 1 (missing = automatic)
        self.rules = defaults()
        self.map = MAP_VOTE
        self.pool = (1 << nmaps) - 1    # every map
        self.state = 0                  # 0 lobby, 1 launching, 2 in a match
        self.go = 0
        self.launch_at = 0.0
        self.launch_members = []
        self.mid = None
        self.touched = now

    def mask_pool(self, allowed):
        """The pool restricted to the map indices `allowed` (iterable), in index order."""
        return [i for i in sorted(allowed) if self.pool >> i & 1]


class Lobbies:
    def __init__(self, nmaps=25, now=time.time, rand=secrets.choice, log=lambda *a: None):
        self.now = now
        self.rand = rand
        self.log = log
        self.nmaps = max(1, min(int(nmaps), 31))
        self.lock = threading.RLock()
        self.by_code = {}               # code -> Lobby
        self.of = {}                    # token -> code
        self.seen = {}                  # token -> last poll
        self.mids = {}                  # match id -> code (a private match; kept until forget_mid)
        self.mid_rules = {}             # match id -> rules dict copy at the start
        self.mid_members = {}           # match id -> set of lobby members at the start (late join)

    # ---------------------------------------------------------------- reads
    def lobby_of(self, token):
        with self.lock:
            c = self.of.get(token)
            return self.by_code.get(c) if c else None

    def in_lobby(self, token):
        return self.lobby_of(token) is not None

    def is_private_mid(self, mid):
        with self.lock:
            return mid in self.mids

    def rules_of_mid(self, mid):
        with self.lock:
            r = self.mid_rules.get(mid)
            return dict(r) if r else None

    def rule(self, mid, key):
        """A rule of the private match `mid`, None for a public match."""
        r = self.rules_of_mid(mid)
        return None if r is None else r.get(key, RULES[key][0])

    def jip_ok(self, token, mid):
        """Join in progress: may `token` be put into the running match `mid`? A private match takes only its own lobby's members (LATE JOIN on);
        a member of a lobby goes only into its own lobby's match, never into a public one."""
        with self.lock:
            code = self.of.get(token)
            if mid in self.mids:
                return bool(self.mid_rules.get(mid, {}).get("late", 1)) and (token in self.mid_members.get(mid, ()) or code == self.mids[mid])
            return code is None

    def on_enqueue(self, token):
        """A search started. A member of a lobby that is not launching / playing searches publicly: it leaves the lobby (the ext's public
        FIND MATCH). Returns True when it left."""
        with self.lock:
            lb = self.lobby_of(token)
            if lb and lb.state == 0:
                self._leave(token)
                self.log("PRIVATE public search - left", lb.code)
                return True
        return False

    # ---------------------------------------------------------------- writes
    def _new_code(self):
        for _ in range(200):
            c = "".join(self.rand(CODE_ALPHABET) for _ in range(CODE_LEN))
            if c not in self.by_code:
                return c
        raise RuntimeError("no free lobby code")

    def touch(self, token):
        with self.lock:
            self.seen[token] = self.now()

    def create(self, token):
        with self.lock:
            lb = self.lobby_of(token)
            if lb and lb.owner == token and lb.state == 0:
                return lb, ""
            if lb and lb.state != 0:
                return None, "busy"
            self._leave(token)
            lb = Lobby(self._new_code(), token, self.now(), self.nmaps)
            self.by_code[lb.code] = lb
            self.of[token] = lb.code
            self.seen[token] = self.now()
            self.log("PRIVATE create", lb.code)
            return lb, ""

    def join(self, token, code):
        code = norm_code(code)
        with self.lock:
            lb = self.by_code.get(code)
            if not lb:
                return None, "nocode"
            if token in lb.members:
                return lb, ""
            if lb.state == 2 and not lb.rules.get("late", 1):
                return None, "started"
            if len(lb.members) >= min(MAX_MEMBERS, lb.rules.get("maxp", MAX_MEMBERS)):
                return None, "full"
            cur = self.lobby_of(token)
            if cur and cur.state != 0:
                return None, "busy"
            self._leave(token)
            lb.members.append(token)
            self.of[token] = code
            self.seen[token] = self.now()
            lb.touched = self.now()
            self.log("PRIVATE join", code, len(lb.members))
            return lb, ""

    def leave(self, token):
        with self.lock:
            return self._leave(token)

    def _leave(self, token):
        code = self.of.pop(token, None)
        lb = self.by_code.get(code) if code else None
        if not lb:
            return False
        if token in lb.members:
            lb.members.remove(token)
        lb.team.pop(token, None)
        if token in lb.launch_members:
            lb.launch_members.remove(token)
        if not lb.members:
            self.by_code.pop(code, None)
            self.log("PRIVATE closed", code)
        elif lb.owner == token:
            lb.owner = lb.members[0]
            self.log("PRIVATE owner left", code, "- new owner = the oldest member")
        lb.touched = self.now()
        return True

    def set(self, token, arg):
        """SET "<key>=<int>" (owner). Returns (lobby, err)."""
        with self.lock:
            lb = self.lobby_of(token)
            if not lb:
                return None, "nolobby"
            if lb.owner != token:
                return lb, "notowner"
            if lb.state != 0:
                return lb, "busy"
            k, _, v = (arg or "").partition("=")
            k = k.strip()
            try:
                iv = int(v, 16) if k == "pool" else int(v)
            except ValueError:
                return lb, "badvalue"
            if k == "map":
                if iv not in (MAP_VOTE, MAP_RANDOM) and not (0 <= iv < self.nmaps):
                    return lb, "badvalue"
                lb.map = iv
                if iv >= 0:
                    lb.pool |= 1 << iv              # a chosen map is always in the pool
            elif k == "pool":
                iv &= (1 << self.nmaps) - 1
                if not iv:
                    return lb, "emptypool"          # never an empty pool
                lb.pool = iv
                if lb.map >= 0 and not iv >> lb.map & 1:
                    lb.map = MAP_VOTE               # the chosen map left the pool: back to a vote
            elif valid(k, iv):
                lb.rules[k] = iv
                if k == "maxp" and len(lb.members) > iv:
                    pass                            # nobody is removed; only new joins are refused
            else:
                return lb, "badrule"
            lb.touched = self.now()
            return lb, ""

    def set_team(self, token, arg):
        with self.lock:
            lb = self.lobby_of(token)
            if not lb:
                return None, "nolobby"
            if lb.state != 0:
                return lb, "busy"
            a, _, b = (arg or "").partition("=")
            try:
                k, t = int(a), int(b)
            except ValueError:
                return lb, "badvalue"
            if not (0 <= k < len(lb.members)) or t not in (0, 1, AUTO):
                return lb, "badvalue"
            who = lb.members[k]
            mode = lb.rules.get("teams", 0)
            if not ((mode == 1 and token == lb.owner) or (mode == 2 and (token == who or token == lb.owner))):
                return lb, "teamsauto" if mode == 0 else "notallowed"
            if t == AUTO:
                lb.team.pop(who, None)
            else:
                lb.team[who] = t
            return lb, ""

    def kick(self, token, arg):
        with self.lock:
            lb = self.lobby_of(token)
            if not lb:
                return None, "nolobby"
            if lb.owner != token:
                return lb, "notowner"
            try:
                k = int(arg)
            except (TypeError, ValueError):
                return lb, "badvalue"
            if not (1 <= k < len(lb.members)):
                return lb, "badvalue"
            self._leave(lb.members[k])
            return lb, ""

    def start(self, token):
        with self.lock:
            lb = self.lobby_of(token)
            if not lb:
                return None, "nolobby"
            if lb.owner != token:
                return lb, "notowner"
            if lb.state != 0:
                return lb, "busy"
            lb.state = 1
            lb.go += 1
            lb.launch_at = self.now()
            lb.launch_members = list(lb.members)
            self.log("PRIVATE start", lb.code, len(lb.members), "member(s)")
            return lb, ""

    def cancel(self, token):
        with self.lock:
            lb = self.lobby_of(token)
            if not lb:
                return None, "nolobby"
            if lb.owner != token:
                return lb, "notowner"
            if lb.state == 1:
                lb.state = 0
                lb.launch_members = []
            return lb, ""

    # ---------------------------------------------------------------- matchmaker side
    def split_ready(self, ready):
        """(public tokens, private tokens): lobby members never enter a public match while they are in a lobby."""
        with self.lock:
            pub = [t for t in ready if t not in self.of]
            return pub, [t for t in ready if t in self.of]

    def launches(self, searching):
        """Lobbies whose match should form now: [(lobby, players)]. `searching` = tokens searching right now (fresh poll). A lobby forms when
        every launch member searches, or LAUNCH_WAIT_S after START with the ones that do (at least one)."""
        now = self.now()
        out = []
        s = set(searching)
        with self.lock:
            for lb in self.by_code.values():
                if lb.state != 1:
                    continue
                want = [t for t in lb.launch_members if t in lb.members]
                have = [t for t in want if t in s]
                if have and (len(have) == len(want) or now - lb.launch_at >= LAUNCH_WAIT_S):
                    out.append((lb, have))
                elif not have and now - lb.launch_at >= 3 * LAUNCH_WAIT_S:
                    lb.state = 0                    # nobody ever searched: back to the lobby
                    self.log("PRIVATE launch timed out", lb.code)
        return out

    def teams_for(self, lb, players, balanced):
        """(team 0, team 1) for the private match. `balanced(players)` = the daemon's own balanced split for automatic players."""
        mode = lb.rules.get("teams", 0)
        if mode == 0:
            return balanced(players)
        t0 = [p for p in players if lb.team.get(p) == 0]
        t1 = [p for p in players if lb.team.get(p) == 1]
        rest = [p for p in players if p not in t0 and p not in t1]
        for p in rest:                              # automatic ones fill the smaller team
            (t0 if len(t0) <= len(t1) else t1).append(p)
        return t0, t1

    def bound(self, lb, mid, players):
        with self.lock:
            lb.state = 2
            lb.mid = mid
            self.mids[mid] = lb.code
            self.mid_rules[mid] = dict(lb.rules, map=lb.map, pool=lb.pool)
            self.mid_members[mid] = set(lb.members)
            while len(self.mids) > 256:
                old = next(iter(self.mids))
                self.forget_mid(old)
        self.log("PRIVATE match", lb.code, mid, len(players), "player(s)")

    def match_over(self, mid):
        """The match ended (or was called off): its lobby goes back to state 0 so the owner can start the next one."""
        with self.lock:
            code = self.mids.get(mid)
            lb = self.by_code.get(code) if code else None
            if lb and lb.mid == mid:
                lb.state = 0
                lb.mid = None
                lb.launch_members = []

    def aborted(self, mid):
        """The match never got going and its players were put back in the queue (MatchMaker.abort): the lobby launches again with them."""
        with self.lock:
            code = self.mids.get(mid)
            lb = self.by_code.get(code) if code else None
            if lb and lb.state in (0, 2) and lb.mid in (mid, None):
                lb.state = 1
                lb.mid = None
                lb.launch_at = self.now()
                lb.launch_members = list(lb.members)
                self.log("PRIVATE match called off - launching again", lb.code, mid)

    def forget_mid(self, mid):
        with self.lock:
            self.mids.pop(mid, None)
            self.mid_rules.pop(mid, None)
            self.mid_members.pop(mid, None)

    def gc(self, alive=lambda t: False):
        """Members that stopped polling leave (unless `alive(token)` says they are in a match). Returns the number removed."""
        now = self.now()
        n = 0
        with self.lock:
            for t in list(self.of):
                lb = self.lobby_of(t)
                if lb and lb.state == 2:
                    continue                        # in the match: the ext does not poll the lobby
                if now - self.seen.get(t, 0) > MEMBER_TTL and not alive(t):
                    self._leave(t); n += 1
            # idle = no change AND no member poll for LOBBY_IDLE_S (a group waiting on the lobby page keeps it)
            for c in [c for c, lb in self.by_code.items()
                      if lb.state != 2 and now - max([lb.touched] + [self.seen.get(t, 0) for t in lb.members]) > LOBBY_IDLE_S]:
                for t in list(self.by_code[c].members):
                    self._leave(t)
                self.by_code.pop(c, None)
        return n

    # ---------------------------------------------------------------- wire
    @staticmethod
    def parse(pl):
        """[64B token][u8 ver][u8 sub][ASCII arg] -> (token, sub, arg) or None"""
        if len(pl) < 66:
            return None
        tok = pl[:64].decode("latin1", "ignore")
        return tok, pl[65], pl[66:130].decode("ascii", "ignore").strip()

    def state_text(self, token, name_of, err=""):
        with self.lock:
            lb = self.lobby_of(token)
            out = ["ok=%d" % (0 if err else 1)]
            if err:
                out.append("err=%s" % err)
            if not lb:
                out.append("in=0")
                return " ".join(out)
            out += ["in=1", "code=%s" % lb.code, "own=%d" % (1 if lb.owner == token else 0), "me=%d" % lb.members.index(token),
                    "st=%d" % lb.state, "go=%d" % lb.go, "n=%d" % len(lb.members), "map=%d" % lb.map, "pool=%x" % lb.pool]
            out += ["%s=%d" % (k, lb.rules[k]) for k in RULES]
            for k, t in enumerate(lb.members):
                out += ["p%d=%s" % (k, clean_name(name_of(t))), "t%d=%d" % (k, lb.team.get(t, AUTO)), "h%d=%d" % (k, 1 if t == lb.owner else 0)]
            return " ".join(out)

    def rules_text(self, mid):
        r = self.rules_of_mid(mid) if mid else None
        if r is None:
            return "pm=0"
        return " ".join(["pm=1", "mid=%s" % mid] + ["%s=%d" % (k, v) for k, v in r.items()])
