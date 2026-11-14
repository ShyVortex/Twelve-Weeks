"""Queue stays after a match: after a match ends, everybody in that queue
goes straight to finding match (but the lobby waits for everyone to be done with stuff like post match summary screens etc); the text
changes from Finding match.. to Waiting for players.. for that duration.

When a match ends (MatchMaker.end) every player still in it whose t2r-ext can requeue (0xE3 flag 0x20 during the match) gets a TICKET:
  state 'post'   the match is over, the player is on the scoreboard / post-match screens (its ext searches by itself once the MP menu is back);
  state 'search' it is searching again (MatchMaker.enqueue).
While a group (= the players of one finished match) still has a 'post' member that is online and not in another match, and the group is younger
than WAIT_MAX s, its 'search' members are HELD: not matchable (try_form / jip_ready skip them) - the next lobby forms only once everybody is back.
The client of a held player shows WAITING FOR PLAYERS... instead of FINDING MATCH... (the 0xBD reply carries rqw=<players still finishing>).
A ticket ends with: a search cancel (dequeue), a kick / ban / refusal, a new match, going offline, or TICKET_S s after the match end.

Pure bookkeeping (no daemon imports): the caller passes the queue, the presence silence and the in-match test. Thread-safe (own lock; never
calls out while holding it). Log prefix 'requeue:'."""
import threading
import time

POST, SEARCH = "post", "search"


class Requeue:
    def __init__(self, wait_max=120.0, ticket_s=300.0, offline_s=30.0, now=time.time):
        self.wait_max = wait_max      # s after the match end the group waits for its slowest member (then the others search normally)
        self.ticket_s = ticket_s      # s after the match end a player's ext may still search by itself when it reaches the MP menu
        self.offline_s = offline_s    # a 'post' member silent this long (no keepalive / ext poll) is gone: not waited for
        self.now = now
        self.lock = threading.Lock()
        self.t = {}                   # token -> [mid, t_end, state]

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
        with self.lock:
            e = self.t.get(token)
            if e is None:
                return None
            e[2] = SEARCH
            return e[0]

    def drop(self, token):
        """Ticket gone (cancel / kick / ban / new match). True when there was one."""
        with self.lock:
            return self.t.pop(token, None) is not None

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
        return gone

    def held(self, queued, silence, in_match, now=None):
        """Queued tokens to hold back right now + the groups still waiting.
        queued: tokens in the matchmaking queue; silence(token) -> s since its last sign of life; in_match(token) -> bool (a live match).
        Returns (held set, {mid: [tokens still on the post-match screens]}, [(token, why) tickets ended])."""
        now = self.now() if now is None else now
        qs = set(queued)
        toks = self.tokens()
        sil = {t: silence(t) for t in toks}
        inm = {t: bool(in_match(t)) for t in toks}
        with self.lock:
            gone = self._prune(sil, inm, now)
            groups = {}
            for t, (mid, t_end, st) in self.t.items():
                groups.setdefault(mid, []).append((t, t_end, st))
            held, waiting = set(), {}
            for mid, mem in groups.items():
                t_end = min(e[1] for e in mem)
                if now - t_end >= self.wait_max:
                    continue
                post = [t for t, _, st in mem if st == POST]
                srch = [t for t, _, st in mem if st == SEARCH and t in qs]
                if post and srch:
                    held.update(srch)
                    waiting[mid] = post
        return held, waiting, gone

    def status(self, token, queued, silence, in_match, now=None):
        """For the client: (ticket open, number of players its search waits for: 0 = not held)."""
        now = self.now() if now is None else now
        held, waiting, _ = self.held(queued, silence, in_match, now)
        with self.lock:
            e = self.t.get(token)
            if not e or now - e[1] >= self.ticket_s:
                return False, 0
            mid = e[0]
        return True, (len(waiting.get(mid, ())) if token in held else 0)
