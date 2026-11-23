"""Per-team gun limits - daemon side.

The daemon is the single arbiter: every player reports the limited guns of the loadout it intends to spawn with (op 0xDE), the
daemon grants a gun only while fewer than `max` teammates hold it. Two teammates picking in the same instant reach the daemon
one after the other (one lock): the first is granted, the second denied. A holder keeps its gun (re-claims are idempotent), and
loses it by claiming a loadout without it, by leaving / timing out of the match (pruned against the match's active players on
every request), by the match ending, or by not refreshing its claim for CLAIM_TTL s (the ext re-sends it every 2 s in a match).

LIMITS is the table (bit order = bit i of every mask on the wire; tools/ext/gunlimit.c carries the same list, the test compares):
    (weapon ids that count as the gun - loud and suppressed variants, max per team, display name for the message)
Add a row to limit another gun; the message is "Too many of <NAME> on team."

Wire (t2r-ext's own short TCP connection, like op 0xDC):
  ext -> server  0xDE [64B token][u16 mask]       mask = limited guns in the loadout the player will spawn with (0 = none = release)
  server -> ext  0xDF ASCII "k=v ...": on=1 team=<0|1> mask=<what we hold now> grant=<bits of the request that were granted>
                 deny=<bits asked for and refused> full=<bits other teammates hold up to the max: unavailable to this player>
                 pend=<bits asked for, neither granted nor refused yet: pre-match settle window, see below> (new key: an old ext ignores it)
                 on=0 when the token is in no live match (the ext shows no restriction)
PRE-MATCH (nobody may START the match with a second Tactical Shotgun): from the moment the match is formed until the game
start went out (`pre=True`), claims are not first-come-first-served but ranked: every wanter of a gun is kept with its first-claim
time; the ranking is (first claim time in SETTLE_BUCKET s buckets, slot) - earliest claim wins, a tie inside a bucket = lowest slot.
A claim is only decided once it is SETTLE s old (answered `pend` until then), so every claim of the same bucket has arrived by
then and the answer never flips afterwards. The first `max` ranked wanters are granted, the rest denied (the ext switches them to a
class without the gun BEFORE the first spawn). After the game start the old immediate rule applies (holders keep their gun).

Pure logic, no sockets: tools/tests/test_gunlimit.py.
"""
import threading
import time

OP_REQ, OP_REPLY = 0xDE, 0xDF
LIMITS = (
    (("shotgun-tactical", "shotgun-tactical-supp"), 1, "TACTICAL SHOTGUN"),
)
CLAIM_TTL = 45.0
SETTLE = 0.6            # pre-match: a claim is decided this long after its first arrival
SETTLE_BUCKET = 0.25    # pre-match: claims within one bucket tie (lowest slot wins)


def table_ids():
    return [list(ids) for ids, _, _ in LIMITS]


class GunLimits:
    def __init__(self, limits=LIMITS, now=time.time, log=lambda *a: None, ttl=CLAIM_TTL):
        self.limits = limits
        self.now = now
        self.log = log
        self.ttl = ttl
        self.lock = threading.Lock()
        self.held = {}          # mid -> {team -> {bit -> {token: last claim time}}}
        self.want = {}          # mid -> {team -> {bit -> {token: [first claim time, slot, last claim time]}}}  (pre-match ranking)

    def _bits(self, mid, team):
        return self.held.setdefault(mid, {}).setdefault(team, {})

    def _prune(self, mid, active):
        """Drop holders that left the match / stopped refreshing (lock held)."""
        t = self.now()
        for team, bits in self.held.get(mid, {}).items():
            for bit, holders in bits.items():
                for tok in [k for k, at in holders.items() if tok_gone(k, active) or t - at > self.ttl]:
                    del holders[tok]
                    self.log("GUNLIMIT", self.limits[bit][2], "released by", tok[:6], "(left / stale)")

    def claim(self, mid, team, token, mask, active=None, pre=False, slot=0, with_pend=False):
        """One request. Returns (grant, deny, full, held_mask) (+ pend with with_pend). `active` = tokens still in the match (None: no pruning).
        pre = the match has not started yet: ranked + settled decisions (see the header); slot = the player's slot (tie break)."""
        with self.lock:
            if active is not None:
                self._prune(mid, active)
            bits = self._bits(mid, team)
            wants = self.want.setdefault(mid, {}).setdefault(team, {})
            t = self.now()
            grant = deny = full = held = pend = 0
            for i, (_, mx, name) in enumerate(self.limits):
                holders = bits.setdefault(i, {})
                wi = wants.setdefault(i, {})
                for k in [k for k, w in wi.items() if t - w[2] > self.ttl or (active is not None and tok_gone(k, active))]:
                    del wi[k]
                if mask >> i & 1:
                    if token in wi:
                        wi[token][2] = t
                        wi[token][1] = slot
                    else:
                        wi[token] = [t, slot, t]
                else:
                    wi.pop(token, None)
                if mask >> i & 1 and pre and token not in holders:
                    key = lambda k: (int(wi[k][0] / SETTLE_BUCKET), wi[k][1], k)
                    ranked = [k for k in sorted((k for k in wi if k not in holders), key=key)]
                    if t - wi[token][0] < SETTLE:
                        pend |= 1 << i
                    elif ranked.index(token) < mx - len(holders):
                        holders[token] = t
                        grant |= 1 << i
                        self.log("GUNLIMIT", name, "team", team, "pre-match granted to", token[:6], "(earliest claim, slot %d)" % slot)
                    else:
                        deny |= 1 << i
                        self.log("GUNLIMIT", name, "team", team, "pre-match DENIED to", token[:6], "(earlier claim holds it)")
                elif mask >> i & 1:
                    if token in holders or len(holders) < mx:
                        if token not in holders:
                            self.log("GUNLIMIT", name, "team", team, "granted to", token[:6], "(%d/%d)" % (len(holders) + 1, mx))
                        holders[token] = t
                        grant |= 1 << i
                    else:
                        deny |= 1 << i
                        self.log("GUNLIMIT", name, "team", team, "DENIED to", token[:6], "(%d/%d taken)" % (len(holders), mx))
                elif token in holders:
                    del holders[token]
                    self.log("GUNLIMIT", name, "team", team, "released by", token[:6])
                if token in holders:
                    held |= 1 << i
                if len([k for k in holders if k != token]) >= mx:
                    full |= 1 << i
            return (grant, deny, full, held, pend) if with_pend else (grant, deny, full, held)

    def release(self, token):
        """A player left the daemon's matches for good (called on leave; pruning covers every other path)."""
        with self.lock:
            for teams in self.want.values():
                for bits in teams.values():
                    for wi in bits.values():
                        wi.pop(token, None)
            for teams in self.held.values():
                for bits in teams.values():
                    for holders in bits.values():
                        holders.pop(token, None)

    def end(self, mid):
        with self.lock:
            self.held.pop(mid, None)
            self.want.pop(mid, None)

    def export_held(self, mid):
        """JSON-able copy of the held claims of one match ({team: {bit: [tokens]}}) for a daemon restart (the times are not kept)."""
        with self.lock:
            return {str(team): {str(bit): sorted(h) for bit, h in bits.items() if h}
                    for team, bits in self.held.get(mid, {}).items()}

    def import_held(self, mid, data):
        """Restore export_held(): every holder gets a fresh claim time (it refreshes with its next claim, else the TTL frees the gun)."""
        t = self.now()
        with self.lock:
            for team, bits in (data or {}).items():
                for bit, toks in bits.items():
                    holders = self.held.setdefault(mid, {}).setdefault(int(team), {}).setdefault(int(bit), {})
                    for tok in toks:
                        holders[tok] = t

    def gc(self, live_mids):
        with self.lock:
            for mid in [m for m in self.held if m not in live_mids]:
                del self.held[mid]
            for mid in [m for m in self.want if m not in live_mids]:
                del self.want[mid]

    def parse_request(self, pl):
        if len(pl) < 66:
            return None
        token = pl[:64].decode("latin1", "ignore")
        if not all(ch in "0123456789abcdefABCDEF" for ch in token):
            return None
        return token, int.from_bytes(pl[64:66], "little") & ((1 << len(self.limits)) - 1)

    @staticmethod
    def text(on, team=0, held=0, grant=0, deny=0, full=0, pend=0):
        if not on:
            return "on=0"
        return "on=1 team=%d mask=%d grant=%d deny=%d full=%d pend=%d" % (team, held, grant, deny, full, pend)


def tok_gone(token, active):
    return token not in active
