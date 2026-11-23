"""Queue stays after a match ("lets make a queue stay the way it is after a match ends, so after a match ends, everybody in that queue
goes straight to finding match (but the lobby waits for everyone to be done with stuff like post match summary screens etc), maybe change the text
from Finding match.. to Waiting for players.. for that duration").

When a match ends (MatchMaker.end) every player still in it whose t2r-ext can requeue (0xE3 flag 0x20 during the match) gets a TICKET:
  state 'post'   the match is over, the player is on the scoreboard / post-match screens (its ext searches by itself once the MP menu is back);
  state 'search' it is searching again (MatchMaker.enqueue).
While a group (= the players of one finished match) still has a 'post' member that is online and not in another match, and the group is younger
than WAIT_MAX s, its 'search' members are HELD: not matchable (try_form / jip_ready skip them) - the next lobby forms only once everybody is back.
The client of a held player shows WAITING FOR PLAYERS... instead of FINDING MATCH... (the 0xBD reply carries rqw=<players still finishing>).
A ticket ends with: a search cancel (dequeue; only once it searched again - the 0x02 session close right after MATCH-END keeps it), a kick / ban / refusal, a new match, going offline, or TICKET_S s after the match end.

Pure bookkeeping (no daemon imports): the caller passes the queue, the presence silence and the in-match test. Thread-safe (own lock; never
calls out while holding it). Log prefix 'requeue:'.

PERSISTENT LOBBY ("have the lobby not disband after a match ends, seamless, wait for people to get out of the match summary, kinda make it
work like cod lobbies"; approved defaults):
  - release: a waiting group's searchers are released when everybody is back, or RELEASE_S s after its FIRST member searched again, or WAIT_MAX s
    after the match end (whichever comes first); never earlier than MIN_GAP s after the end (the finished match's record lives ~9 s, see _free).
  - a released group is formed FIRST and together (MatchMaker.try_form: ready_groups -> the front of the ready list, the queue backfills the rest);
    its members still on the post-match screens keep their seats (the backfill leaves room for them) and join the new match in progress when they
    are back (formed / next_of -> jip_pass only_mid).
  - lobby(): the group's state for the client's 0xBD reply (back, still on the screens, seconds until the next match)."""
import threading
import time

POST, SEARCH = "post", "search"


class Requeue:
    def __init__(self, wait_max=120.0, ticket_s=300.0, offline_s=30.0, now=time.time, release_s=0.0, min_gap=0.0):
        self.wait_max = wait_max      # s after the match end the group waits for its slowest member (then the others search normally)
        self.ticket_s = ticket_s      # s after the match end a player's ext may still search by itself when it reaches the MP menu
        self.offline_s = offline_s    # a 'post' member silent this long (no keepalive / ext poll) is gone: not waited for
        self.release_s = release_s    # s after the group's first search the others are not waited for any more (0 = only wait_max)
        self.min_gap = min_gap        # s after the match end before the group may form again (0 = at once)
        self.now = now
        self.lock = threading.Lock()
        self.t = {}                   # token -> [mid, t_end, state]
        self.first = {}               # mid -> time its first member searched again
        self.next = {}                # mid -> the match its members formed next (the slow ones join it in progress)

    def open(self, mid, tokens, now=None):
        """The match `mid` ended: tickets for `tokens` (the players still in it, requeue-capable). Returns the tokens given a ticket."""
        now = self.now() if now is None else now
        out = []
        with self.lock:
            for t in tokens:
                if t and t not in out:
                    self.t[t] = [mid, now, POST]
                    out.append(t)
        return out

    def searching(self, token):
        """The token queued again. Returns its group's match id when it holds a ticket (else None)."""
        now = self.now()
        with self.lock:
            e = self.t.get(token)
            if e is None:
                return None
            e[2] = SEARCH
            self.first.setdefault(e[0], now)
            return e[0]

    def drop(self, token):
        """Ticket gone (cancel / kick / ban / new match). True when there was one."""
        with self.lock:
            return self.t.pop(token, None) is not None

    def drop_search(self, token):
        """A search cancel (0x02 outside a match): drops the ticket only when the player was searching again. A 'post' ticket stays: every
 client closes its session with 0x02 about 2 s after MATCH-END, while it is still on the post-match screens. True when dropped."""
        with self.lock:
            e = self.t.get(token)
            if e is None or e[2] != SEARCH:
                return False
            del self.t[token]
            return True

    def has(self, token, now=None):
        now = self.now() if now is None else now
        with self.lock:
            e = self.t.get(token)
            return bool(e) and now - e[1] < self.ticket_s

    def mid_of(self, token):
        with self.lock:
            e = self.t.get(token)
            return e[0] if e else None

    def tokens(self):
        with self.lock:
            return list(self.t)

    def _prune(self, sil, inm, now):
        """(lock held) Tickets that ended: old, offline, or playing another match. sil / inm = the callbacks' answers, taken before the lock
        (the callers' own locks are never taken inside this one: MatchMaker.try_form calls held() with MM.lock held). Returns [(token, why)]."""
        gone = []
        for t, (mid, t_end, st) in list(self.t.items()):
            why = None
            if now - t_end >= self.ticket_s:
                why = "ticket expired (%.0f s after the match end)" % (now - t_end)
            elif inm.get(t):
                why = "in a match again"
            elif st == POST and sil.get(t, 0.0) > self.offline_s:
                why = "offline (silent %.0f s)" % sil[t]
            if why:
                del self.t[t]
                gone.append((t, why))
        live = {e[0] for e in self.t.values()}
        for d in (self.first, self.next):
            for m in [m for m in d if m not in live]:
                del d[m]
        return gone

    def _left(self, mid, t_end, now):
        """(lock held) Seconds until the group `mid` is released by time (wait cap / release timer / min gap)."""
        left = self.wait_max - (now - t_end)
        f = self.first.get(mid)
        if self.release_s > 0 and f is not None:
            left = min(left, self.release_s - (now - f))
        return max(left, self.min_gap - (now - t_end), 0.0)

    def groups(self, queued, silence, in_match, now=None):
        """Every group with a ticket left: {mid: {'post': [tokens on the screens], 'srch': [searching, in the queue], 'end': t_end, 'go': released,
        'left': s until the release by time, 'next': the match formed from it or None}} + [(token, why) tickets ended]."""
        now = self.now() if now is None else now
        qs = set(queued)
        toks = self.tokens()
        sil = {t: silence(t) for t in toks}
        inm = {t: bool(in_match(t)) for t in toks}
        out = {}
        with self.lock:
            gone = self._prune(sil, inm, now)
            for t, (mid, t_end, st) in self.t.items():
                g = out.setdefault(mid, {"post": [], "srch": [], "end": t_end, "go": False, "left": 0.0, "next": self.next.get(mid)})
                g["end"] = min(g["end"], t_end)
                if st == POST:
                    g["post"].append(t)
                elif t in qs:
                    g["srch"].append(t)
            for mid, g in out.items():
                g["left"] = self._left(mid, g["end"], now)
                gap = now - g["end"] < self.min_gap
                g["go"] = not gap and (not g["post"] or g["left"] <= 0.0 or g["next"] is not None)
        return out, gone

    def held(self, queued, silence, in_match, now=None):
        """Queued tokens to hold back right now + the groups still waiting.
        queued: tokens in the matchmaking queue; silence(token) -> s since its last sign of life; in_match(token) -> bool (a live match).
        Returns (held set, {mid: [tokens still on the post-match screens]}, [(token, why) tickets ended])."""
        now = self.now() if now is None else now
        out, gone = self.groups(queued, silence, in_match, now)
        held, waiting = set(), {}
        for mid, g in out.items():
            if g["srch"] and not g["go"]:
                held.update(g["srch"])
                waiting[mid] = list(g["post"])
        return held, waiting, gone

    def ready_groups(self, queued, silence, in_match, now=None):
        """Released groups that have not formed their next match yet, oldest end first: [(mid, [searching tokens in the queue], [tokens still on
        the screens = seats kept])]. The caller forms them first and together."""
        now = self.now() if now is None else now
        out, _ = self.groups(queued, silence, in_match, now)
        res = [(g["end"], mid, list(g["srch"]), list(g["post"])) for mid, g in out.items() if g["go"] and g["srch"] and g["next"] is None]
        return [(mid, srch, post) for _, mid, srch, post in sorted(res)]

    def formed(self, new_mid, tokens):
        """A match formed with `tokens`: their groups' next match is `new_mid` (the members still on the screens join it). Returns the groups."""
        with self.lock:
            gs = {self.t[t][0] for t in tokens if t in self.t}
            for m in gs:
                self.next[m] = new_mid
        return gs

    def kept(self, new_mid, now=None):
        """Tokens whose seat in `new_mid` is kept: members of a group that formed `new_mid` and still hold their ticket (on the post-match screens,
        or back and about to join). An expired ticket keeps nothing."""
        now = self.now() if now is None else now
        with self.lock:
            gs = {m for m, n in self.next.items() if n == new_mid}
            return [t for t, (m, t_end, _) in self.t.items() if m in gs and now - t_end < self.ticket_s]

    def next_of(self, token):
        """The match the token's group formed while it was still on the post-match screens (None: none / no ticket)."""
        with self.lock:
            e = self.t.get(token)
            return self.next.get(e[0]) if e else None

    def status(self, token, queued, silence, in_match, now=None):
        """For the client: (ticket open, number of players its search waits for: 0 = not held)."""
        lb = self.lobby(token, queued, silence, in_match, now)
        return (False, 0) if lb is None else (True, lb["wait"])

    def members(self, token, queued, silence, in_match, now=None):
        """The token's lobby group for the searching page rows: (members searching again, members still on the post-match screens), or None
        (no open ticket). Only while the group still waits (not released, no match formed from it yet)."""
        now = self.now() if now is None else now
        out, _ = self.groups(queued, silence, in_match, now)
        with self.lock:
            e = self.t.get(token)
            if not e or now - e[1] >= self.ticket_s:
                return None
            mid = e[0]
        g = out.get(mid)
        if g is None or g["next"]:
            return None
        return list(g["srch"]), list(g["post"])

    def lobby(self, token, queued, silence, in_match, now=None):
        """The token's lobby for the client, or None (no open ticket): {'wait': players its search waits for (0 = not held), 'back': members
        searching, 'post': members still on the screens, 'left': whole s until the next match forms anyway (0 = not held)}."""
        now = self.now() if now is None else now
        out, _ = self.groups(queued, silence, in_match, now)
        with self.lock:
            e = self.t.get(token)
            if not e or now - e[1] >= self.ticket_s:
                return None
            mid = e[0]
        g = out.get(mid)
        if g is None:
            return {"wait": 0, "back": 0, "post": 0, "left": 0}
        held = token in g["srch"] and not g["go"]
        return {"wait": len(g["post"]) if held else 0, "back": len(g["srch"]), "post": len(g["post"]),
                "left": int(g["left"] + 0.999) if held else 0}
