"""Interrogation (TLOU 2013 Factions game mode) - daemon side. See re/interrogation.md.

Mode select: daemon env T2R_MODE = "supply-raid" (default, nothing changes) | "interrogation" |
"rotate" (alternates per match). The mode is fixed when the match goes live (GAME-START).

Rules kept by the server (the authority for the counters; clients only report their own events):
  * every interrogation (hold E on a downed enemy) gives the interrogator's team 1 intel;
    every KILLS_PER_INFO deaths of the enemy team give 1 more (0 = kills don't count);
  * a team with NEED intel learns where the enemy lockbox is (revealed) and may steal it;
  * stealing = 3 stages of holding E at the enemy lockbox; the hold per stage gets shorter as
    the match goes on (2013: "the lock box becomes easier to open as the match progresses");
    a stage, once done, stays done for the team;
  * the first team to finish stage 3 wins (the clients' t2r-ext then end the match through
    winmm's own match end, FUN_180062b00(team) -> the host's op 0x12); when the match timer runs
    out winmm decides as usual (team with more lives left = fewer deaths = more kills).

Ops (t2r-ext's own short TCP connection, like the clan ops):
  ext -> server  0xDC [64B token][u8 sub][u16 seq][args]
                 sub 0 poll (seq 0; optional arg [u8 0..100] = percent of the lockbox stage the sender is holding E on right now, 0 = not unlocking;
                       the server shows it to both teams as h0/h1 so the safe marker rings fill live while a teammate / the enemy unlocks)
                 sub 1 interrogation done   [u8 victim slot]
                 sub 2 lockbox stage done   [u8 stage 1..3]
                 sub 3 we died              [u8 killer slot, 0xff unknown]
                 seq = per-client event counter (1..65535, wraps): an event resent after a lost
                 reply is booked once
  server -> ext  0xDD ASCII "k=v k=v ..." (state_text)
                 on=0 when the player's match is not an Interrogation match (the ext stays off)

Pure logic, no sockets: tools/tests/test_interrogation.py drives it with a fake clock.
"""
import json
import os
import random
import threading
import time

OP_REQ, OP_REPLY = 0xDC, 0xDD
SUB_POLL, SUB_INTERROGATE, SUB_STAGE, SUB_DIED = 0, 1, 2, 3
MODES = ("supply-raid", "interrogation")
STAGES = 3

_HERE = os.path.dirname(os.path.abspath(__file__))


def load_lockboxes(path=os.path.join(_HERE, "interrogation_lockboxes.json")):
    """map index -> (candidates team 0, candidates team 1), from tools/interrogation_lockboxes.py."""
    try:
        table = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {e["map"]: tuple(max(1, len(t)) for t in e["teams"]) for e in table}


class Interrogation:
    def __init__(self, mode=None, need=None, kills_per_info=None, now=time.time, log=print, rng=None,
                 lockboxes=None, stage_secs=18.0, boost_after=720.0, boost_every=90.0, boost_step=0.12, boost_max=4, locate_secs=20.0, keep=30.0):
        env = os.environ
        self.mode_env = (mode or env.get("T2R_MODE", "supply-raid")).strip().lower()
        self.need = int(need if need is not None else env.get("T2R_INT_NEED", "5"))
        self.kpi = int(kills_per_info if kills_per_info is not None else env.get("T2R_INT_KILLS_PER_INFO", "4"))
        self.now = now
        self.log = log
        self.rng = rng or random.Random()
        self.lockboxes = load_lockboxes() if lockboxes is None else lockboxes
        # (2013 interrogation-notifs.md section 3): ~18 s per stage for ONE unlocker at the start (the video: 17-19 s at a 10 to 11 min clock; was 8 s), then late in the match the
        # unlock speed is raised every ~20 s ("Unlock speed increased!", the video at 6:25 / 6:45 / 7:05 of an 11:00 clock = from ~275 s in): speed = 1 + boost_step * n, hold = stage_secs / speed.
        self.stage_secs = float(stage_secs[0] if isinstance(stage_secs, (tuple, list)) else stage_secs)
        self.boost_after = boost_after
        self.boost_every = boost_every
        self.boost_step = boost_step
        self.boost_max = boost_max
        self.locate_secs = float(env.get("T2R_INT_LOCATE_SECS", locate_secs))    # 2013: the reveal comes ~20 s after the intel is complete ("All intel gathered! Locating lockbox..." 3:28 -> "located!" 3:48)
        self.keep = keep                  # an ended match answers polls this long (late clients see the win)
        self.lock = threading.Lock()
        self.matches = {}                 # mid -> record
        self.by_token = {}                # token -> mid
        self._rot = 0

    # ------------------------------------------------------------ mode select
    def pick_mode(self):
        m = self.mode_env
        if m in ("int", "interrogation"):
            return "interrogation"
        if m == "rotate":
            self._rot += 1
            return MODES[self._rot % 2]       # first rotated match = interrogation
        return "supply-raid"

    # ------------------------------------------------------------ match lifecycle
    def start(self, mid, players, map_idx=0, team_of=lambda slot: slot % 2, mode=None):
        """The match went live. Returns the mode. Supply Raid matches are not recorded."""
        mode = mode or self.pick_mode()
        with self.lock:
            self._drop(mid)
            if mode != "interrogation":
                return mode
            if self.lockboxes and map_idx not in self.lockboxes:   # a map without lockbox positions (SP-section maps): nobody could win
                self.log("INTERROGATION: map", map_idx, "has no lockboxes - Supply Raid match")
                return "supply-raid"
            nb = self.lockboxes.get(map_idx, (1, 1))
            rec = {"players": list(players), "team": {t: team_of(i) for i, t in enumerate(players)},
                   "map": map_idx, "t0": self.now(), "intel": [0, 0], "kills": [0, 0],
                   "stage": [0, 0], "stage_at": [0.0, 0.0], "box": [self.rng.randrange(nb[0]), self.rng.randrange(nb[1])],
                   "win": -1, "ended": None, "seq": {}}
            self.matches[mid] = rec
            for t in players:
                self.by_token[t] = mid
        self.log("INTERROGATION start", mid, "map", map_idx, "lockboxes", rec["box"], "need", self.need, "kpi", self.kpi)
        return mode

    def roster(self, mid, players, team_of=lambda slot: slot % 2):
        """join in progress (Interrogation matches are joinable): the match's player list changed in place (slot = index).
        The joiner gets its team from its slot; the intel / kills / stages of both teams are kept."""
        with self.lock:
            r = self.matches.get(mid)
            if not r:
                return
            r["players"] = list(players)
            for i, t in enumerate(players):
                r["team"][t] = team_of(i)
                self.by_token[t] = mid
        self.log("INTERROGATION roster", mid, "now", len(players), "slots")

    def end(self, mid, winner=None):
        """The host's op 0x12 arrived: freeze the record (dropped after `keep` s)."""
        with self.lock:
            r = self.matches.get(mid)
            if r and r["ended"] is None:
                r["ended"] = self.now()
                if r["win"] < 0 and winner in (0, 1):
                    r["win"] = winner
                self.log("INTERROGATION end", mid, "winner", r["win"], "intel", r["intel"], "stages", r["stage"])

    def drop(self, mid):
        with self.lock:
            self._drop(mid)

    def _drop(self, mid):
        r = self.matches.pop(mid, None)
        if r:
            for t in r["players"]:
                if self.by_token.get(t) == mid:
                    self.by_token.pop(t, None)

    def _rec(self, token):
        mid = self.by_token.get(token)
        r = self.matches.get(mid) if mid is not None else None
        if r and r["ended"] is not None and self.now() - r["ended"] > self.keep:
            self._drop(mid)
            return None
        return r

    # ------------------------------------------------------------ rules
    def progress(self, r, team):
        return r["intel"][team] + (r["kills"][team] // self.kpi if self.kpi > 0 else 0)

    def intel_full(self, r, team):
        """The team has all its intel ('All intel gathered! Locating lockbox...'); the moment is stamped once."""
        if self.progress(r, team) < self.need:
            return False
        full_at = r.setdefault("full_at", [None, None])
        if full_at[team] is None:
            full_at[team] = self.now()
        return True

    def revealed(self, r, team):
        """The lockbox is located locate_secs after the intel is complete."""
        return self.intel_full(r, team) and self.now() - r["full_at"][team] >= self.locate_secs

    def speed_level(self, r):
        """Number of 'Unlock speed increased!' steps so far (0 before boost_after s)."""
        el = self.now() - r["t0"]
        if el < self.boost_after or self.boost_every <= 0:
            return 0
        return min(self.boost_max, int((el - self.boost_after) // self.boost_every) + 1)

    def hold_secs(self, r):
        """Seconds of holding E per lockbox stage for one unlocker: stage_secs at speed 1, shorter with each speed step."""
        return round(self.stage_secs / (1.0 + self.boost_step * self.speed_level(r)), 2)

    def is_new(self, r, token, seq):
        if not seq:
            return True                                 # unnumbered event (old ext): always booked
        last = r["seq"].get(token)
        if last is not None and not (0 < ((seq - last) & 0xFFFF) < 0x8000):
            return False
        r["seq"][token] = seq
        return True

    def event(self, token, sub, seq=0, args=b""):
        """One request from a client. Returns the reply text."""
        with self.lock:
            r = self._rec(token)
            if r and sub == SUB_POLL and args and r["ended"] is None and r["win"] < 0:
                r.setdefault("hold", {})[token] = (min(int(args[0]), 100), self.now())      # live unlock progress of this client's current stage
            if r and sub != SUB_POLL and r["ended"] is None and r["win"] < 0 and self.is_new(r, token, seq):
                self._apply(r, token, sub, args)
            return self._text(r, token)

    def _apply(self, r, token, sub, args):
        team = r["team"].get(token, 0)
        slots = {i: t for i, t in enumerate(r["players"])}
        if sub == SUB_INTERROGATE and args:
            victim = slots.get(args[0])
            if victim is None or r["team"].get(victim) == team:
                self.log("INTERROGATION refused (no enemy in slot %d)" % args[0])
                return
            before = self.intel_full(r, team)
            r["intel"][team] += 1
            self.log("INTERROGATION team", team, "intel", r["intel"][team], "progress", self.progress(r, team), "/", self.need)
            if not before and self.intel_full(r, team):
                self.log("INTERROGATION team", team, "has all intel - lockbox located in", self.locate_secs, "s")
        elif sub == SUB_DIED:
            enemy = 1 - team
            before = self.intel_full(r, enemy)
            r["kills"][enemy] += 1
            if not before and self.intel_full(r, enemy):
                self.log("INTERROGATION team", enemy, "has all intel (kills) - lockbox located in", self.locate_secs, "s")
        elif sub == SUB_STAGE and args:
            stage = args[0]
            if not self.revealed(r, team):
                self.log("INTERROGATION stage refused (team %d has no intel)" % team)
                return
            if stage != r["stage"][team] + 1 or stage > STAGES:
                return                                  # stale / skipped stage: ignore
            r["stage"][team] = stage
            r["stage_at"][team] = self.now()
            for t in [t for t in r.get("hold", {}) if r["team"].get(t) == team]:
                r["hold"].pop(t, None)                  # the stage is done: its live progress restarts at 0
            self.log("INTERROGATION team", team, "lockbox stage", stage, "/", STAGES)
            if stage == STAGES:
                r["win"] = team
                self.log("INTERROGATION team", team, "stole the lockbox - wins")

    def live_hold(self, r, team):
        """Percent (0..100) of the stage a team's unlockers are on: the highest fresh report (< 3 s old) of a client of that team."""
        now = self.now()
        best = 0
        for t, (pct, at) in r.get("hold", {}).items():
            if r["team"].get(t) == team and now - at < 3.0 and r["stage"][team] < STAGES:
                best = max(best, pct)
        return best

    def _text(self, r, token):
        if not r:
            return "on=0 mode=supply-raid"
        team = r["team"].get(token, 0)
        p = [min(self.progress(r, t), 99) for t in (0, 1)]
        f = {"on": 1, "mode": "interrogation", "map": r["map"], "team": team, "need": self.need,
             "kpi": self.kpi, "i0": r["intel"][0], "i1": r["intel"][1], "k0": r["kills"][0], "k1": r["kills"][1],
             "p0": p[0], "p1": p[1], "rev0": int(self.revealed(r, 0)), "rev1": int(self.revealed(r, 1)),
             "box0": r["box"][0], "box1": r["box"][1], "st0": r["stage"][0], "st1": r["stage"][1],
             "hold": self.hold_secs(r), "sp": self.speed_level(r), "h0": self.live_hold(r, 0), "h1": self.live_hold(r, 1), "win": r["win"], "ended": int(r["ended"] is not None),
             "seq": r["seq"].get(token, 0)}
        return " ".join("%s=%s" % kv for kv in f.items())

    def parse_request(self, pl):
        """0xDC payload -> (token, sub, seq, args) or None."""
        if len(pl) < 65:
            return None
        token = pl[:64].decode("latin1", "ignore")
        if not all(ch in "0123456789abcdefABCDEF" for ch in token):
            return None
        sub = pl[64]
        seq = int.from_bytes(pl[65:67], "little") if len(pl) >= 67 else 0
        return token, sub, seq, pl[67:]
