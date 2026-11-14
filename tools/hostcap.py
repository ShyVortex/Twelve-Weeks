"""Host upload capacity (re/host-capacity-1019.md): a 4v4 host must upload ~0.9-1.7 MB/s; many home lines cannot, and then the
whole match lags. The daemon remembers, per player token, what upload that player has PROVEN as a host and whether a match lagged while
that player hosted, and the host pick / re-pick consult it.

Data (all optional, backward compatible): the ext appends 7 bytes to its 30 s performance report (op 0xCA, after the 72 byte v1 body):
    [u8 capver=1][u16 LE avg tx KB/s][u16 LE peak tx KB/s (10 s window)][u8 worst msg-7 REAL loss x10 %][u8 samples]
The tx numbers are what the reporter's own game really sent (only large while it hosts); the loss is what it received through the
host's relay (a client's view of the host's upload).  An old ext sends nothing: the player stays 'unknown' (neutral). An old daemon
ignores the extra bytes.

T2R_HOST_CAP: 0 off (nothing recorded, no log), 1 record + log only, 2 the pick / re-pick use it (live, DEFAULT: match 82599fb6,
a ~1 Mbit host lagged the lobby to 800-970 ms and was never replaced).
The history lives in the daemon's sqlite db (table host_cap, one row per token): it outlives matches and daemon restarts. Schema v2
adds lag_mid (the match the latest lag record belongs to), so 'lagged in THIS match' survives a daemon restart and a restart no longer
charges the same match twice.
Pure logic + a tiny sqlite table; tests: tools/tests/test_hostcap.py."""
import os, time


def _envi(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


MODE = _envi("T2R_HOST_CAP", 2)
NEED_KB_PER_EXTRA = _envi("T2R_HOST_CAP_KB_PER_EXTRA", 225)   # ~0.22 MB/s per player besides the host (4 players ~0.66 MB/s, 8 ~1.5 MB/s: re/ext-bandwidth-1019.md)
WINDOW_MS = _envi("T2R_HOST_CAP_WINDOW_MS", 40)                # capacity only decides among candidates within this many ms of the best worst-ping key
LAG_LOSS10 = _envi("T2R_HOST_CAP_LOSS10", 30)                  # a client's msg-7 REAL loss >= 3.0 % in 2 reports in a row = the host's link is struggling
LAG_DAYS = _envi("T2R_HOST_CAP_LAG_DAYS", 30)                  # a lag record older than this no longer counts
LAG_WINDOW_MS = _envi("T2R_HOST_CAP_LAG_WINDOW_MS", 150)       # a host that LAGGED at this lobby size loses to a not-lagged candidate up to this much worse
MIN_PLAYERS = 3                                                # 2 players: no relay, nothing to prove
SCHEMA = 2                                                     # host_cap columns: v1 + lag_mid (v2)


NEED_KB_PER_PAIR = _envi("T2R_HOST_CAP_KB_PER_PAIR", 46)       # Live logs: the star relay sends every player's state to every other client, so the load grows with (n-1)^2
                                                               # (measured on one host: 5 players 700-800 KB/s, 8 players 1940-2470 KB/s = ~46-50 KB/s per (n-1)^2)


def need_kb(n_players):
    """KB/s a host needs for a lobby of n_players (documented estimate)."""
    return NEED_KB_PER_EXTRA * max(0, n_players - 1)


def need_kb_relay(n_players):
    """Measured relay load (quadratic in the lobby size) - what a ping-only handover target must have PROVEN in a big lobby (see proven_for)."""
    extra = max(0, n_players - 1)
    return max(need_kb(n_players), NEED_KB_PER_PAIR * extra * extra)


def parse_cap(pl):
    """The optional trailer of an op 0xCA payload (the 72 byte v1 body first) -> dict or None (old ext / short / bad version)."""
    if len(pl) < 72 + 7 or pl[72] != 1:
        return None
    return {"avg_kb": int.from_bytes(pl[73:75], "little"), "peak_kb": int.from_bytes(pl[75:77], "little"),
            "loss10": pl[77], "n": pl[78]}


def parse_oneway(pl):
    """Alarm trailer 2 of an op 0xCA payload (flags bit1 set; after the 7 byte capacity trailer): the reporter SENT but received nothing for a while
    (re/oneway-p2p-1019.md).  -> {"quiet_s", "rx_pkts", "tx_kb", "in_match_s"} or None (old ext / no alarm / short)."""
    if len(pl) < 72 + 7 + 7 or not (pl[71] & 2) or pl[72] != 1 or pl[79] != 1:
        return None
    return {"quiet_s": pl[80], "rx_pkts": int.from_bytes(pl[81:83], "little"), "tx_kb": int.from_bytes(pl[83:85], "little"), "in_match_s": pl[85]}


class HostCap:
    """Per-token host capacity history. connect() -> sqlite3 connection (the daemon's db())."""

    def __init__(self, connect, now=time.time, log=print):
        self.connect = connect
        self.now = now
        self.log = log
        self.streak = {}            # (mid, token) -> consecutive lossy client reports
        self.mlag = {}              # mid -> host token already charged with a lag in this match
        self._schema_ok = False

    def _ensure(self, c):
        """host_cap at SCHEMA (create, or add the v2 column to a v1 table). Runs once per instance."""
        c.execute("""CREATE TABLE IF NOT EXISTS host_cap(token TEXT PRIMARY KEY, hosted INT DEFAULT 0, best_kb INT DEFAULT 0,
            best_n INT DEFAULT 0, last_kb INT DEFAULT 0, lag_n INT DEFAULT 0, lag_t REAL DEFAULT 0, ceil_kb INT DEFAULT 0, last_t REAL DEFAULT 0)""")
        if "lag_mid" not in {r[1] for r in c.execute("PRAGMA table_info(host_cap)")}:
            c.execute("ALTER TABLE host_cap ADD COLUMN lag_mid TEXT")
        c.commit()
        self._schema_ok = True

    def _q(self, fn):
        c = self.connect()
        try:
            if not self._schema_ok:
                self._ensure(c)
            try:
                return fn(c)
            except Exception as e:
                if "no such table" not in str(e) and "no such column" not in str(e):
                    raise
                self._ensure(c)
                return fn(c)
        finally:
            c.close()

    def get(self, token):
        def f(c):
            r = c.execute("SELECT hosted,best_kb,best_n,last_kb,lag_n,lag_t,ceil_kb,last_t,lag_mid FROM host_cap WHERE token=?", (token,)).fetchone()
            return None if not r else dict(zip(("hosted", "best_kb", "best_n", "last_kb", "lag_n", "lag_t", "ceil_kb", "last_t", "lag_mid"), r))
        return self._q(f)

    def lagged_in(self, mid, token):
        """True when token was charged with a lag while hosting match mid (in memory, or from the db after a daemon restart)."""
        if mid is None:
            return False
        if self.mlag.get(mid) == token:
            return True
        r = self.get(token)
        return bool(r and r.get("lag_mid") == str(mid))

    def _upd(self, token, **kw):
        def f(c):
            c.execute("INSERT OR IGNORE INTO host_cap(token) VALUES(?)", (token,))
            c.execute("UPDATE host_cap SET " + ",".join("%s=?" % k for k in kw) + " WHERE token=?", list(kw.values()) + [token])
            c.commit()
        self._q(f)

    # ---- one-way inbound (re/oneway-p2p-1019.md): the ext of a player in a match sent for seconds and received nothing. RECORDED and LOGGED only;
    # the host pick does not use it (a recommendation is in the note).
    def oneway_note(self, token, mid=None, host=False):
        def f(c):
            c.execute("CREATE TABLE IF NOT EXISTS oneway(token TEXT PRIMARY KEY, n INT DEFAULT 0, host_n INT DEFAULT 0, last_t REAL DEFAULT 0, last_mid TEXT)")
            c.execute("INSERT OR IGNORE INTO oneway(token) VALUES(?)", (token,))
            c.execute("UPDATE oneway SET n=n+1, host_n=host_n+?, last_t=?, last_mid=? WHERE token=?", (1 if host else 0, self.now(), mid, token))
            c.commit()
            return c.execute("SELECT n, host_n FROM oneway WHERE token=?", (token,)).fetchone()
        return self._q(f)

    def oneway_get(self, token, days=30):
        """(alarms, as host) in the last `days` days, or (0, 0). last_t only keeps the latest, so an old record counts as nothing."""
        def f(c):
            try:
                r = c.execute("SELECT n, host_n, last_t FROM oneway WHERE token=?", (token,)).fetchone()
            except Exception:
                return (0, 0)
            return (r[0], r[1]) if r and self.now() - r[2] <= days * 86400 else (0, 0)
        return self._q(f)

    # ---- evidence
    def host_report(self, token, n_players, avg_kb, peak_kb=0, mid=None):
        """The match HOST's own report: its real tx. Raises the proven capacity unless the match is already known to lag."""
        if n_players < MIN_PLAYERS or avg_kb <= 0:
            return
        r = self.get(token) or {}
        kw = {"last_kb": int(avg_kb), "last_t": self.now(), "hosted": (r.get("hosted") or 0) + 1}
        lagged = self.lagged_in(mid, token)
        if not lagged and avg_kb > (r.get("best_kb") or 0):
            kw.update(best_kb=int(avg_kb), best_n=int(n_players))
        self._upd(token, **kw)

    def client_report(self, mid, host_token, token, loss10):
        """A client's view: its msg-7 REAL loss through the host. 2 reports in a row >= LAG_LOSS10 = one lag record for the host (once per match)."""
        k = (mid, token)
        if loss10 < LAG_LOSS10:
            self.streak[k] = 0
            return False
        self.streak[k] = self.streak.get(k, 0) + 1
        if self.streak[k] < 2 or self.lagged_in(mid, host_token):
            return False
        return self.note_lag(host_token, mid)

    def note_lag(self, host_token, mid=None):
        """The match lagged while host_token hosted: remember it and the tx level it lagged at (a ceiling the host cannot carry)."""
        if mid is not None:
            self.mlag[mid] = host_token
        r = self.get(host_token) or {}
        kw = {"lag_n": (r.get("lag_n") or 0) + 1, "lag_t": self.now()}
        if mid is not None:
            kw["lag_mid"] = str(mid)
        last = r.get("last_kb") or 0
        if last > 0:
            kw["ceil_kb"] = min(last, r["ceil_kb"]) if r.get("ceil_kb") else last
        self._upd(host_token, **kw)
        return True

    def forget_matches(self, live_mids):
        for d in (self.streak, self.mlag):
            for k in [k for k in d if (k[0] if isinstance(k, tuple) else k) not in live_mids]:
                del d[k]

    def proven_for(self, token, n_players):
        """True when token has PROVEN the measured relay load of an n_players lobby as a host (best tx >= need_kb_relay) and has no recent lag record."""
        r = self.get(token)
        if not r or not r.get("best_kb") or r["best_kb"] < need_kb_relay(n_players):
            return False
        return not (r.get("lag_n") and self.now() - r["lag_t"] <= LAG_DAYS * 86400)

    # ---- decision
    def verdict(self, token, n_players):
        """(rank, text): 0 proven enough, 1 unknown / unproven (neutral), 2 lagged as host (recent record whose ceiling is below the need, or no ceiling,
        and never proven enough for this lobby size). A lag record contradicted by proven capacity (live db: hosts that carried 1.5-3 MB/s at
        8 players with a 'ceiling' of ~230 KB/s - the loss came from a client's own line) is neutral, not rank 2."""
        r = self.get(token)
        need = need_kb(n_players)
        if not r:
            return 1, "unknown"
        recent_lag = r["lag_n"] and self.now() - r["lag_t"] <= LAG_DAYS * 86400
        if recent_lag:
            ceil = r["ceil_kb"]
            if not ceil or need > ceil * 0.9:
                if r["best_kb"] >= need:
                    return 1, "proven %d KB/s (need %d) but lagged x%d at ~%d KB/s" % (r["best_kb"], need, r["lag_n"], ceil)
                return 2, "lagged x%d at ~%d KB/s (need %d)" % (r["lag_n"], ceil, need)
        if r["best_kb"] >= need:
            return 0, "proven %d KB/s (need %d)" % (r["best_kb"], need)
        if r["best_kb"]:
            return 1, "unproven: best %d KB/s at %d players (need %d)" % (r["best_kb"], r["best_n"], need)
        return 1, "unknown"


def pick(cands, n_players, verdict, window_ms=None, label=str):
    """cands: [(player, key)] with key = hostmig.host_key (worst ping incl. penalty, total). Returns (chosen, lines): among the candidates within
    window_ms (worst ping) of the best key, the one with the lowest verdict rank; ties by key. When that one LAGGED as host at this lobby size
    (rank 2), a not-lagged candidate up to LAG_WINDOW_MS worse wins instead (a lagging host costs everyone far more than that)."""
    w = WINDOW_MS if window_ms is None else window_ms
    ranked = sorted(cands, key=lambda c: c[1])
    if not ranked:
        return None, []
    best = ranked[0]
    wide = [c for c in ranked if c[1][0] - best[1][0] <= max(w, LAG_WINDOW_MS)]
    vs = {c[0]: verdict(c[0], n_players) for c in wide}
    near = [c for c in wide if c[1][0] - best[1][0] <= w]
    chosen = min(near, key=lambda c: (vs[c[0]][0], c[1]))
    if vs[chosen[0]][0] >= 2:
        ok = [c for c in wide if vs[c[0]][0] < 2]
        if ok:
            chosen = min(ok, key=lambda c: (vs[c[0]][0], c[1]))
            near = near + [c for c in ok if c not in near]
    lines = ["%s worst %d total %d: %s" % (label(c[0]), c[1][0], c[1][1], vs[c[0]][1]) for c in near]
    return chosen[0], lines
