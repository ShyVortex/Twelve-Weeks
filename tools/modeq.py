"""Per-mode matchmaking queues (FIND MATCH opens SUPPLY RAID / INTERROGATION, each with a live count of the players searching in it).

The client picks the mode in its own menu and tells the daemon before it starts the search (t2r-ext short connection, like the clan ops):

  ext -> server  0xBC [64B token][u8 sub][u8 mode]     sub 0 = poll the counts, sub 1 = my next search is for `mode`
                 mode = the row id of tools/modes.json (0 supply-raid, 1 interrogation)
  server -> ext  0xBD ASCII "q0=<n> q1=<n> .. qN-1=<n> mode=<m> forced=<0|1>" (one q per row of tools/modes.json)   n = players searching right now in that mode (the caller included)

The queue itself stays one MatchMaker queue; every token has a preference (`pref`) and a match only forms from players of ONE mode
(MatchMaker.try_form -> ModeQ.group). A party searches in its leader's mode. Daemon env T2R_MODE (anything but empty) FORCES the mode of
every match as before: the preferences are then ignored by the queue (counts are still reported, forced=1).
QUICK MATCH: a client that sees "any=1" in the reply may send mode ANY (255) = "any mode": the token sits in every
mode's queue (counts add it to each mode) and joins the lobby that can start soonest, preferring the mode that already has players waiting;
old clients never send it, an old daemon refuses it (set() -> False) and does not report "any=1", so a new client falls back to the default mode.
A token that never sent a preference is Supply Raid (clients without the picker, auto-find) - nothing changes for them."""
import os
import threading
import time

OP_REQ, OP_REPLY = 0xBC, 0xBD
try:
    import gen_modes
    MODES = tuple(e["key"] for e in gen_modes.load())          # tools/modes.json: THE list of modes (a new mode = a new row there + python tools/gen_modes.py)
except Exception:                                              # noqa: BLE001 - never breaks the daemon
    MODES = ("supply-raid", "interrogation")
NMODES = len(MODES)
ANY = 255                              # wire value of QUICK MATCH (any mode)
PREF_TTL = 3600.0                      # a picked mode is forgotten after an hour without a new pick


def forced():
    """True when the operator pinned the mode with T2R_MODE (testing / rotation): the player's pick does not matter then."""
    return bool(os.environ.get("T2R_MODE", "").strip())


class ModeQ:
    def __init__(self, now=time.time):
        self.now = now
        self.lock = threading.Lock()
        self.pref = {}                 # token -> (mode idx, time)
        self.mmode = {}                # match id -> mode name of the group it was formed from
        self.rr = 0                    # rotation for lobbies made only of ANY searchers (no mode has players waiting)

    def set(self, token, mode):
        if not isinstance(mode, int) or not (0 <= mode < NMODES or mode == ANY):
            return False
        with self.lock:
            self.pref[token] = (mode, self.now())
        return True

    def get(self, token, leader=None):
        """The mode `token` searches in (its party leader's pick when `leader` is given)."""
        with self.lock:
            e = self.pref.get(leader or token) or self.pref.get(token)
            if e and self.now() - e[1] <= PREF_TTL:
                return e[0]
        return 0

    def group(self, ready, leader_of):
        """Restrict the matchable tokens `ready` (oldest first) to one mode: the first mode with a lobby worth forming (>= 2 players), else the
        mode of the oldest searcher. Returns (ready filtered, mode name or None when modes are off)."""
        if forced() or not ready:
            return ready, None
        by = {m: [] for m in range(NMODES)}
        anys = []
        for t in ready:
            m = self.get(t, leader_of(t))
            (anys if m == ANY else by[m]).append(t)
        if not anys:
            order = sorted((m for m in by if by[m]), key=lambda m: ready.index(by[m][0]))
            pick = next((m for m in order if len(by[m]) >= 2), order[0])
            return by[pick], MODES[pick]
        # QUICK MATCH searchers fit every lobby: the mode that can start soonest = most players of that mode already waiting (a lobby that
        # has players), then the oldest waiting; a lobby needs >= 2 players with the ANY ones counted in
        def key(m):
            return (-len(by[m]), ready.index(by[m][0]) if by[m] else len(ready))
        live = [m for m in range(NMODES) if len(by[m]) + len(anys) >= 2]
        if live and all(not by[m] for m in live):           # only ANY searchers: rotate so every mode gets matches
            pick = (self.rr % NMODES)
            self.rr += 1
        else:
            pick = min(live or range(NMODES), key=key)
        grp = set(by[pick]) | set(anys)
        return [t for t in ready if t in grp], MODES[pick]

    def fits(self, token, mid, leader=None):
        """May `token` be put into the running match `mid` (join in progress)?"""
        if forced():
            return True
        with self.lock:
            mm = self.mmode.get(mid)
        g = self.get(token, leader)
        return mm is None or g == ANY or mm == MODES[g]

    def counts(self, queue_tokens, leader_of):
        c = [0] * NMODES
        for t in queue_tokens:
            m = self.get(t, leader_of(t))
            if m == ANY:                       # searching in every mode
                c = [n + 1 for n in c]
            else:
                c[m] += 1
        return c

    def total(self, queue_tokens):
        return len(queue_tokens)

    @staticmethod
    def compat(a, b):
        """Do searchers with picks a and b share a lobby? (search page list)"""
        return a == b or a == ANY or b == ANY

    def formed(self, mid, mode):
        if mode:
            with self.lock:
                self.mmode[mid] = mode
                while len(self.mmode) > 64:
                    self.mmode.pop(next(iter(self.mmode)))

    def match_mode(self, mid):
        if forced():
            return None
        with self.lock:
            return self.mmode.get(mid)

    @staticmethod
    def parse(pl):
        """[64B token][u8 sub][u8 mode] -> (token, sub, mode) or None"""
        if len(pl) < 65:
            return None
        tok = pl[:64].decode("latin1", "ignore")
        return tok, pl[64], pl[65] if len(pl) > 65 else 0

    @staticmethod
    def reply(q, mode, is_forced, total=None):
        """mode = the caller's pick as the client's row index (ANY = NMODES = the QUICK MATCH row); "any=1" tells the client this daemon takes
        ANY; qa = players searching in any mode (everyone)."""
        if mode == ANY:
            mode = NMODES
        return (" ".join("q%d=%d" % (i, n) for i, n in enumerate(q)) + " mode=%d forced=%d any=1 qa=%d" % (mode, 1 if is_forced else 0, sum(q) if total is None else total))
