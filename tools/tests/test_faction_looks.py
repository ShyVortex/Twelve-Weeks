"""Offline test of the faction look sync (re/faction-looks.md): compiles the REAL protocol core
(tools/ext/faction_look_core.h, the code t2r-ext.c runs) into a small DLL and plays whole matches
with it - 2 to 4 clients, star topology through the host with latency and message loss, winmm's
match flow (intro spawn in state 3, puppets created when positions arrive in state 4/5, the
match-start spawn seconds later, deaths, respawn grants 0xc from the host), late join, host
migration, team swaps between matches. Checks that every screen shows each player with the look
that player has on its own screen, that teammates differ, and that the puppet spawn gate (peer+5)
never moves state.
Run: python tools/tests/test_faction_looks.py   (plain python; needs the msys2 gcc of tools/win/ext,
found in this checkout or the main one; no game, no network)."""
import ctypes, heapq, os, random, re, subprocess, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path.insert(0, os.path.join(TOOLS, "features"))

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

# ---------------------------------------------------------------- build the core
WRAP = r'''
#define FL_API __declspec(dllexport)
#include "faction_look_core.h"
__declspec(dllexport) int fl_size(void) { return (int)sizeof(fl_core_t); }
__declspec(dllexport) int fl_get(const fl_core_t *c, int what, int s) {
    switch (what) {
    case 0: return c->seq; case 1: return c->cur; case 2: return c->next; case 3: return c->team;
    case 10: return c->shown[s].valid; case 11: return c->shown[s].idx; case 12: return c->shown[s].seq;
    case 13: return c->shown[s].team; case 14: return c->shown[s].died; case 15: return c->shown[s].bound;
    case 16: return c->shown[s].heals;
    case 20: return c->peer[s].valid; case 21: return c->peer[s].cur; case 22: return c->peer[s].next;
    case 23: return c->peer[s].seq; case 24: return c->peer[s].team;
    }
    return -1;
}
'''

def build():
    gcc = None
    for base in (ROOT, MAIN):
        p = os.path.join(base, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if os.path.exists(p):
            gcc = p
            break
    if not gcc:
        print("SKIP: no gcc (tools/win/ext/msys64)")
        sys.exit(0)
    tmp = tempfile.mkdtemp(prefix="fltest")
    src, dll = os.path.join(tmp, "w.c"), os.path.join(tmp, "flcore.dll")
    open(src, "w").write(WRAP)
    env = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ.get("PATH", ""))
    subprocess.check_call([gcc, "-std=gnu2x", "-O2", "-shared", "-static", "-I", os.path.join(TOOLS, "ext"),
                           "-o", dll, src], env=env)
    L = ctypes.CDLL(dll)
    u64, u32, P = ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p
    L.fl_core_init.argtypes = [P, u32, u64]
    L.fl_core_set_team.argtypes = [P, ctypes.c_int]
    L.fl_core_state.argtypes = [P, ctypes.c_uint8]
    L.fl_core_own_spawn.argtypes = [P, ctypes.c_int, u64]
    L.fl_core_msg.argtypes = [P, ctypes.c_char_p]
    L.fl_core_next_fix.argtypes = [P]
    L.fl_core_set_pool.argtypes = [P, ctypes.c_int, ctypes.c_int]
    L.fl_core_warm.argtypes = [P, ctypes.c_int, ctypes.c_int]
    L.fl_core_recv.argtypes = [P, u32, ctypes.c_char_p, u64, u64]
    L.fl_core_puppet_dead.argtypes = [P, u32]
    L.fl_core_peer_reset.argtypes = [P, u32]
    L.fl_core_puppet_spawn.argtypes = [P, u32, ctypes.c_int, ctypes.c_int, u64, P]
    L.fl_core_rebind.argtypes = [P, u32]
    L.fl_core_heal_want.argtypes = [P, u32]
    L.fl_core_healed.argtypes = [P, u32, u64]
    L.fl_get.argtypes = [P, ctypes.c_int, ctypes.c_int]
    return L

L = build()
N = 6                                    # FL_MALE_N: the pool every pick uses unless a female mode widens it (scen_pools checks it)

class Core:
    def __init__(self, me, seed):
        self.buf = ctypes.create_string_buffer(L.fl_size())
        self.p = ctypes.addressof(self.buf)
        L.fl_core_init(self.p, me, seed)
    def g(self, what, s=0): return L.fl_get(self.p, what, s)
    def snapshot(self): return bytes(self.buf)

# ---------------------------------------------------------------- the simulated game
FRAME = 16

class Client:
    def __init__(self, sim, slot, team):
        self.sim, self.slot, self.team = sim, slot, team
        self.core = Core(slot, sim.rng.getrandbits(64) | 1)
        self.state = 0            # winmm match state (+0x2b80)
        self.lobby = True         # team lobby (+0x1b0 == 2)
        self.present = True
        self.model = None         # own look (team, idx) on its own screen
        self.alive = False
        self.dead_known = [False] * 4
        self.pup = [None] * 4     # puppet of slot s: dict(look, alive, ms)
        self.winmm_str = [None] * 4
        self.spawn_str = [None] * 4
        self.heal_ms = [-10**9] * 4
        self.next_send = 0
        self.load_ms = None
        self.heals = 0
        self.spawn_ms = 0
        self.wait_since = [None] * 4

    # winmm's team rule for us: -1 outside the team lobby / match
    def raw_team(self):
        return self.team if (self.lobby or self.state >= 3) else -1

    def own_str(self):
        c = self.core
        seq, cur, nxt, team = c.g(0), c.g(1), c.g(2), c.g(3)
        return (team, cur if seq else nxt)

    def send_msg(self):
        b = ctypes.create_string_buffer(8)
        n = L.fl_core_msg(self.core.p, b)
        if n:
            self.sim.broadcast(self.slot, "look", b.raw[:n], lossy=True)

    def own_spawn(self, kind):
        L.fl_core_state(self.core.p, self.state)
        if not (self.core.g(3) in (0, 1) and self.state >= 3):
            L.fl_core_set_team(self.core.p, self.raw_team())
        new = L.fl_core_own_spawn(self.core.p, kind, self.sim.now)
        if new:
            self.spawn_ms = self.sim.now
        self.model = self.own_str()
        self.alive = True
        self.warm(self.model)
        if new:
            self.send_msg()

    def puppet_spawn(self, s, dead, kind=0):
        before = self.core.snapshot()
        r = L.fl_core_puppet_spawn(self.core.p, s, kind, 1 if dead else 0, self.sim.now, None)
        if r == -2:
            self.sim.gate_calls += 1
            if self.core.snapshot() != before:
                self.sim.gate_moves += 1
            return
        if r >= 0:
            self.wait_since[s] = None
            look = (self.core.g(13, s), r)
        else:
            # no message yet: the ext holds the spawn up to FL_WAIT_MS (winmm's tick retries)
            if self.wait_since[s] is None:
                self.wait_since[s] = self.sim.now
            if self.sim.now - self.wait_since[s] < 2500:
                self.pup[s] = None
                return
            self.wait_since[s] = None
            look = self.winmm_str[s] or (self.sim.clients[s].team, 0)    # winmm default = pool idx 0
        self.pup[s] = dict(look=look, alive=True, ms=self.sim.now)
        self.spawn_str[s] = look
        self.warm(look)

    def warm(self, look):
        if look and look[0] in (0, 1) and 0 <= look[1] < N:
            if look not in self.sim.warm_seen.setdefault(self.slot, set()):
                self.sim.warm_seen[self.slot].add(look)
                self.sim.first_spawns += 1
            L.fl_core_warm(self.core.p, look[0], look[1])

    def recv(self, src, kind, data):
        if not self.present:
            return
        if kind == "look":
            L.fl_core_recv(self.core.p, src, data, len(data), self.sim.now)
        elif kind == "death":
            self.dead_known[src] = True
            if self.pup[src]:
                self.pup[src]["alive"] = False
        elif kind == "grant":                # 0xc respawn grant for slot `data`
            s = data
            if s == self.slot:
                self.own_spawn(1)
            elif self.state >= 3:
                self.dead_known[s] = False
                self.pup[s] = None                       # FUN_1800507a0 removes the old puppet
                self.puppet_spawn(s, False, 1)   # FUN_1800507a0 -> FUN_18004f2d0 (RESPAWN)

    def frame(self):
        if not self.present:
            return
        sim, now = self.sim, self.sim.now
        L.fl_core_state(self.core.p, self.state)
        if now % 480 < FRAME and not (self.core.g(3) in (0, 1) and 3 <= self.state <= 6):
            L.fl_core_set_team(self.core.p, self.raw_team())
        in_match = self.state == 6
        for s, o in enumerate(sim.clients):
            if s == self.slot or o is None:
                continue
            if in_match and self.dead_known[s]:
                L.fl_core_puppet_dead(self.core.p, s)
            # winmm's per-peer tick: a puppet appears once positions arrive (sender in state 4+)
            if self.state >= 3 and o.present and o.state >= 4 and self.pup[s] is None and \
                    now >= sim.visible_at.get((self.slot, s), 10**12):
                self.puppet_spawn(s, self.dead_known[s])
            if self.dead_known[s] and self.state >= 3:
                self.puppet_spawn(s, True)   # tick calls while dead: the gate must keep state
        if now >= self.next_send:
            self.next_send = now + 1000
            if 3 <= self.state <= 6 or self.lobby:
                in_load = 3 <= self.state <= 6
                if not in_load or (in_match and self.alive and self.core.g(0) and now - self.spawn_ms > 1000):
                    L.fl_core_next_fix(self.core.p)
                self.send_msg()
        # heal check (every 30 frames in the ext)
        if in_match and now % 480 < FRAME:
            for s in range(4):
                p = self.pup[s]
                if s == self.slot or not p or not p["alive"]:
                    continue
                want = L.fl_core_heal_want(self.core.p, s)
                if want < 0:
                    continue
                exp = (self.core.g(24, s), want)
                if self.spawn_str[s] == exp:
                    L.fl_core_rebind(self.core.p, s)
                    continue
                if self.core.g(16, s) >= 2 or now - p["ms"] < 3000 or now - self.heal_ms[s] < 10000:
                    continue
                self.heal_ms[s] = now
                self.heals += 1
                L.fl_core_healed(self.core.p, s, now)
                self.puppet_spawn(s, False)

class Sim:
    def __init__(self, seed, teams, loss=0.1, lat=(20, 120)):
        self.rng = random.Random(seed)
        self.now = 0
        self.q = []
        self.n = 0
        self.loss, self.lat = loss, lat
        self.host = 0
        self.gap_until = -1
        self.warm_seen = {}
        self.first_spawns = 0
        self.session_at = -1      # gameplay session start: nothing gets through before it
        self.clients = [Client(self, s, t) if t is not None else None for s, t in enumerate(teams)]
        self.visible_at = {}
        self.gate_calls = self.gate_moves = 0
        self.wrong = {}           # (viewer, slot) -> ms shown wrong
        self.wrong_runs = []      # lengths of wrong stretches
        self.run = {}
        self.same_team_ms = self.team_ms = 0
        self.checked_ms = 0
        self.deaths = 0

    def delay(self, src, dst):
        hops = 1 if self.host in (src, dst) else 2
        return sum(self.rng.randint(*self.lat) for _ in range(hops))

    def send(self, src, dst, kind, data, lossy):
        if self.now < self.gap_until or self.now < self.session_at:
            return                                   # host migration gap: nothing gets through
        if lossy and self.rng.random() < self.loss:
            return
        heapq.heappush(self.q, (self.now + self.delay(src, dst), self.n, dst, src, kind, data))
        self.n += 1

    def broadcast(self, src, kind, data, lossy):
        for d, c in enumerate(self.clients):
            if c is not None and d != src and c.present:
                self.send(src, d, kind, data, lossy)

    def deliver(self):
        while self.q and self.q[0][0] <= self.now:
            _, _, dst, src, kind, data = heapq.heappop(self.q)
            c = self.clients[dst]
            if c is not None:
                c.recv(src, kind, data)

    def step(self, ms):
        end = self.now + ms
        while self.now < end:
            self.deliver()
            for c in self.clients:
                if c is not None:
                    c.frame()
            self.sample()
            self.now += FRAME

    # the invariant: a live puppet shows its player's own look
    def sample(self):
        for v in self.clients:
            if v is None or not v.present or v.state != 6:
                continue
            for s, o in enumerate(self.clients):
                if o is None or s == v.slot or not o.present:
                    continue
                p = v.pup[s]
                key = (v.slot, s)
                if p and p["alive"] and o.alive and o.state == 6:
                    self.checked_ms += FRAME
                    if p["look"] != o.model:
                        self.wrong[key] = self.wrong.get(key, 0) + FRAME
                        self.run[key] = self.run.get(key, 0) + FRAME
                        continue
                if self.run.get(key):
                    self.wrong_runs.append(self.run.pop(key))
        # teammates (own models) differ
        live = [c for c in self.clients if c is not None and c.present and c.state == 6 and c.alive]
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                if live[i].team == live[j].team:
                    self.team_ms += FRAME
                    if live[i].model == live[j].model:
                        self.same_team_ms += FRAME

    # ---- winmm match flow
    def load(self, c, stagger=0):
        """match load for client c: state 3 (+ intro spawn), 4/5 black wait, positions visible"""
        c.lobby = False
        c.state = 3
        c.own_spawn(0)                               # FUN_1800336f0 intro teleport -> FUN_180050870
        c.state = 4
        c.load_ms = self.now
        for o in self.clients:
            if o is None or o is c:
                continue
            self.visible_at[(o.slot, c.slot)] = max(self.now + stagger, self.session_at) + self.delay(c.slot, o.slot)
            if o.state >= 4:
                self.visible_at[(c.slot, o.slot)] = max(self.now, self.session_at) + self.delay(o.slot, c.slot)

    def start(self, c):
        c.state = 6
        c.own_spawn(0)                               # FUN_1800235f0 match-start spawn

    def end_match(self):
        for c in self.clients:
            if c is None:
                continue
            c.state = 0
            c.lobby = True
            c.alive = False
            c.model = None
            c.pup = [None] * 4
            c.dead_known = [False] * 4
        self.visible_at = {}
        self.grants = []                             # respawn grants die with the match
        self.q = [e for e in self.q if e[4] == "look"]   # and winmm's in-flight match events
        heapq.heapify(self.q)

    def kill(self, s):
        c = self.clients[s]
        if not c.alive:
            return
        c.alive = False
        self.deaths += 1
        self.broadcast(s, "death", None, lossy=False)
        self.grants.append((self.now + self.rng.randint(2600, 6000), s))

    def play(self, ms, death_every=(4000, 12000)):
        """a match period: random deaths, host respawn grants"""
        end = self.now + ms
        self.grants = getattr(self, "grants", [])
        next_death = self.now + self.rng.randint(*death_every)
        while self.now < end:
            if self.now >= next_death and self.now >= self.gap_until:
                alive = [c.slot for c in self.clients if c is not None and c.present and c.alive and c.state == 6]
                if alive:
                    self.kill(self.rng.choice(alive))
                next_death = self.now + self.rng.randint(*death_every)
            for g in list(self.grants):
                if g[0] <= self.now and self.now >= self.gap_until:
                    self.grants.remove(g)
                    s = g[1]
                    if self.clients[s] is None or not self.clients[s].present:
                        continue
                    host = self.clients[self.host]
                    for d, c in enumerate(self.clients):     # 0xc to everybody + host applies
                        if c is None or not c.present:
                            continue
                        if d == self.host:
                            host.recv(self.host, "grant", s)
                        else:
                            self.send(self.host, d, "grant", s, lossy=False)
            self.step(FRAME)

def run_match(sim, lobby_ms=4000, start_spread=(1500, 12000), play_ms=90000):
    sim.step(lobby_ms)
    for c in sim.clients:
        if c is not None and c.present:
            sim.load(c, stagger=sim.rng.randint(0, 3000))
    sim.step(sim.rng.randint(*start_spread))          # waiting for players (often > 3 s)
    for c in sim.clients:
        if c is not None and c.present:
            sim.start(c)
    sim.play(play_ms)

def report(name, sim, max_run=0):
    total_wrong = sum(sim.wrong.values())
    longest = max(sim.wrong_runs + list(sim.run.values()) + [0])
    check(sim.checked_ms > 0, f"{name}: puppets were checked ({sim.checked_ms // 1000} s of puppet time, {sim.deaths} deaths)")
    if max_run == 0:
        check(total_wrong == 0, f"{name}: every puppet shows its player's own look (wrong {total_wrong} ms)")
    else:
        check(longest <= max_run, f"{name}: wrong looks healed within {max_run} ms (longest {longest} ms, total {total_wrong} ms)")
    check(sim.gate_moves == 0, f"{name}: puppet spawn calls while dead never move state ({sim.gate_calls} calls)")

# ---------------------------------------------------------------- scenarios
def scen_1v1():
    sims = [Sim(seed, [1, 0], loss=0.1) for seed in range(20)]
    for s in sims:
        for _ in range(3):
            run_match(s)
            s.end_match()
    agg = Sim(0, [1, 0])
    for s in sims:
        agg.checked_ms += s.checked_ms; agg.deaths += s.deaths
        agg.gate_calls += s.gate_calls; agg.gate_moves += s.gate_moves
        for k, v in s.wrong.items(): agg.wrong[k] = agg.wrong.get(k, 0) + v
    report("1v1 x20 seeds, 3 matches each, 10% loss", agg)

def scen_2v2():
    tot = same = 0
    starts_same = starts = 0
    agg = Sim(0, [1, 1, 0, 0])
    for seed in range(15):
        s = Sim(100 + seed, [1, 1, 0, 0], loss=0.1)
        for m in range(3):
            s.step(4000)
            for c in s.clients:
                s.load(c, stagger=s.rng.randint(0, 3000))
            s.step(s.rng.randint(1500, 12000))
            for c in s.clients:
                s.start(c)
            for a, b in ((0, 1), (2, 3)):
                starts += 1
                starts_same += s.clients[a].model == s.clients[b].model
            s.play(90000)
            s.end_match()
            if m == 1:                                 # team swap before the third match
                for c in s.clients:
                    c.team ^= 1
        tot += s.team_ms; same += s.same_team_ms
        agg.checked_ms += s.checked_ms; agg.deaths += s.deaths
        agg.gate_calls += s.gate_calls; agg.gate_moves += s.gate_moves
        for k, v in s.wrong.items(): agg.wrong[k] = agg.wrong.get(k, 0) + v
    report("2v2 x15 seeds, 3 matches (team swap), 10% loss", agg)
    check(starts_same == 0, f"2v2: teammates start every match with different looks ({starts_same}/{starts} same)")
    check(same <= tot * 0.02, f"2v2: teammates look the same < 2% of the time ({100.0 * same / max(tot, 1):.2f}%)")

def scen_late_join(stale):
    agg = Sim(0, [1, 0, 1])
    for seed in range(15):
        s = Sim(200 + seed, [1, 0, 1], loss=0.1)
        s.clients[2].present = False
        s.step(4000)
        for c in s.clients[:2]:
            s.load(c)
        s.step(3000)
        for c in s.clients[:2]:
            s.start(c)
        s.play(20000)
        j = s.clients[2]                              # joins mid match
        j.present = True
        for o in s.clients[:2]:
            # winmm's join packet carries the sender's look string: current, or stale (variant)
            j.winmm_str[o.slot] = (o.team, (o.model[1] + 1) % N) if stale else o.model
        if stale:
            s.loss = 1.0                              # + every message lost for 5 s: the held spawn
        s.load(j)                                     # times out, winmm's stale string, heal
        s.step(500)
        s.start(j)
        s.play(4500)
        s.loss = 0.1
        s.play(55500)
        agg.checked_ms += s.checked_ms; agg.deaths += s.deaths
        agg.gate_calls += s.gate_calls; agg.gate_moves += s.gate_moves
        agg.wrong_runs += s.wrong_runs + list(s.run.values())
        for k, v in s.wrong.items(): agg.wrong[k] = agg.wrong.get(k, 0) + v
        agg.heals = getattr(agg, "heals", 0) + j.heals
    name = "late join, winmm string " + ("stale" if stale else "current")
    report(name, agg, max_run=9000 if stale else 5000)
    if stale:
        check(getattr(agg, "heals", 0) > 0, f"{name}: the joiner healed puppets ({getattr(agg, 'heals', 0)} heals)")

def scen_session_late():
    """in game: the gameplay session (and our slot) only starts with the match - the intro
    spawn, the black wait and every look message before it go nowhere. First puppet spawns then
    have no message yet: they are held up to 2.5 s for it."""
    agg = Sim(0, [1, 1, 0, 0])
    for seed in range(15):
        s = Sim(400 + seed, [1, 1, 0, 0], loss=0.1)
        for m in range(2):
            s.session_at = 10 ** 12
            s.step(4000)
            for c in s.clients:
                s.load(c, stagger=s.rng.randint(0, 3000))
            s.step(s.rng.randint(1500, 12000))
            for c in s.clients:
                s.start(c)
            s.session_at = s.now
            for a_ in s.clients:
                for b_ in s.clients:
                    if a_ is not b_:
                        s.visible_at[(a_.slot, b_.slot)] = s.now + s.delay(b_.slot, a_.slot)
            s.play(60000)
            s.end_match()
        agg.checked_ms += s.checked_ms; agg.deaths += s.deaths
        agg.gate_calls += s.gate_calls; agg.gate_moves += s.gate_moves
        for k, v in s.wrong.items(): agg.wrong[k] = agg.wrong.get(k, 0) + v
    report("session starts with the match (no messages before), first spawns held", agg)

def scen_host_migration():
    agg = Sim(0, [1, 1, 0, 0])
    for seed in range(15):
        s = Sim(300 + seed, [1, 1, 0, 0], loss=0.1)
        s.step(4000)
        for c in s.clients:
            s.load(c)
        s.step(4000)
        for c in s.clients:
            s.start(c)
        s.play(30000)
        # host (slot 0) crashes: 2-5 s of silence, slot 1 takes over, slot 0 is gone
        s.clients[0].present = False
        s.clients[0].alive = False
        s.gap_until = s.now + s.rng.randint(2000, 5000)
        s.host = 1
        s.grants = [g for g in s.grants if g[1] != 0]
        s.step(6000)
        for c in s.clients[1:]:
            L.fl_core_peer_reset(c.core.p, 0)        # the ext clears a slot empty for 2 s
            c.pup[0] = None
        s.play(60000)
        agg.checked_ms += s.checked_ms; agg.deaths += s.deaths
        agg.gate_calls += s.gate_calls; agg.gate_moves += s.gate_moves
        for k, v in s.wrong.items(): agg.wrong[k] = agg.wrong.get(k, 0) + v
    report("host migration (host leaves, 2-5 s gap)", agg)

def scen_old_bug():
    """the old ext advanced a life at BOTH match-start spawns when they were > 3 s apart: with the
    core's START kind the second one is the same life"""
    c = Core(0, 12345)
    L.fl_core_set_team(c.p, 1)
    L.fl_core_state(c.p, 3)
    a = L.fl_core_own_spawn(c.p, 0, 1000)
    L.fl_core_state(c.p, 6)
    b = L.fl_core_own_spawn(c.p, 0, 9000)
    check(a == 1 and b == 0 and c.g(0) == 1, "intro spawn + match-start spawn 8 s apart = one life")
    r = L.fl_core_own_spawn(c.p, 1, 20000)
    check(r == 1 and c.g(0) == 2, "a respawn grant starts a new life")
    L.fl_core_state(c.p, 0)
    L.fl_core_state(c.p, 3)
    check(L.fl_core_own_spawn(c.p, 0, 60000) == 1 and c.g(0) == 3, "the next match load starts a new life")
    L.fl_core_set_team(c.p, -1)
    check(c.g(3) == 1, "team -1 (no team lobby state) keeps the known team (was: flipped to Seraphites)")
    m, m2 = ctypes.create_string_buffer(8), ctypes.create_string_buffer(8)
    n = L.fl_core_msg(c.p, m)
    L.fl_core_msg(c.p, m2)
    v = Core(1, 99)
    old = bytes(m.raw[:5]) + b"\x01"
    check(L.fl_core_recv(v.p, 0, old, 6, 0) == -1, "a version-1 message (old 4-look pool) is ignored")
    check(n == 7 and L.fl_core_recv(v.p, 0, m2.raw[:7], 7, 0) >= 0, "a version-2 message is taken")
    check(L.fl_core_recv(v.p, 0, m.raw[:7], 7, 0) == -2, "an older copy arriving late is dropped (reordered relay)")
    u = Core(2, 7)
    check(L.fl_core_own_spawn(u.p, 0, 100) == -1 and u.g(0) == 0, "team not known: no own life, winmm's look stays")
    check(L.fl_core_msg(u.p, ctypes.create_string_buffer(8)) == 0, "team not known: nothing announced")
    check(L.fl_core_set_team(u.p, -1) == 0 and u.g(2) == 255, "team -1 picks nothing (was: Seraphite default)")
    L.fl_core_set_team(u.p, 1)
    L.fl_core_own_spawn(u.p, 0, 200)
    L.fl_core_set_team(u.p, 0)
    check(u.g(3) == 0 and u.g(1) == 255, "team change forgets the current look (it was the other side's)")
    w = Core(3, 11)
    L.fl_core_set_team(w.p, 0)
    L.fl_core_warm(w.p, 0, 2)
    picks = set()
    for k in range(40):
        L.fl_core_own_spawn(w.p, 1, 1000 + 5000 * k)
        picks.add(w.g(1))
    check(picks == set(range(N)), f"a lone player's lives use all {N} looks ({sorted(picks)}; the warm rule locked it to 2)")
    # receiver-side unit cases (viewer v, sender c = slot 0)
    def msg(t):
        b = ctypes.create_string_buffer(8)
        L.fl_core_msg(c.p, b)
        return L.fl_core_recv(v.p, 0, b.raw[:7], 7, t)
    msg(61000)
    r = L.fl_core_puppet_spawn(v.p, 0, 0, 0, 61100, None)
    check(r == c.g(1), "first sight of a living player: its current look")
    check(L.fl_core_puppet_spawn(v.p, 0, 0, 1, 61200, None) == -2 and v.g(11, 0) == r, "spawn call while dead (peer+5): no change")
    nxt = c.g(2)
    r2 = L.fl_core_puppet_spawn(v.p, 0, 1, 0, 70000, None)          # respawn grant before its message
    check(r2 == nxt, "respawn grant before the message: their announced next look")
    L.fl_core_own_spawn(c.p, 1, 70050)
    check(msg(70100) & 2 == 0 and c.g(1) == r2, "their new life's message agrees (no mismatch)")
    L.fl_core_own_spawn(c.p, 1, 80000)
    msg(80050)                                                          # message first this time
    check(L.fl_core_puppet_spawn(v.p, 0, 1, 0, 80100, None) == c.g(1), "message before the grant: their new look")
    # winmm's dead-puppet recovery (FUN_1800507a0) while the player lived on: taken for a new life,
    # 2 s of messages still telling the old life -> heal wants their current look back
    cur = c.g(1)
    L.fl_core_puppet_spawn(v.p, 0, 1, 0, 90000, None)
    check(L.fl_core_heal_want(v.p, 0) == -1, "recovery spawn: no heal before their messages had time")
    msg(91000); msg(92500)
    check(L.fl_core_heal_want(v.p, 0) == cur, "recovery spawn that was no new life: heal back to their current look")

def scen_pools():
    """ext FACTION_LOOKS == dc_data_patches.FACTION_LOOKS, FL_N matches"""
    import dc_data_patches
    src = open(os.path.join(TOOLS, "ext", "t2r-ext.c"), encoding="utf-8", errors="replace").read()
    m = re.search(r"FACTION_LOOKS\[2\]\[FL_N\] = \{(.*?)\n\};", src, re.S)
    rows = re.findall(r"\{([^{}]*)\}", m.group(1)) if m else []
    ext = [re.findall(r'"([^"]+)"', r) for r in rows]
    hdr = open(os.path.join(TOOLS, "ext", "faction_look_core.h"), encoding="utf-8").read()
    n = int(re.search(r"#define FL_N (\d+)", hdr).group(1))
    nm = int(re.search(r"#define FL_MALE_N (\d+)", hdr).group(1))
    py, fem = dc_data_patches.FACTION_LOOKS, dc_data_patches.FEMALE_LOOKS
    check(len(ext) == 2 and [r[:nm] for r in ext] == [py["seraphite"], py["wlf"]],
          f"ext male pool == dc_data_patches pool ({[r[:nm] for r in ext]})")
    check(len(ext) == 2 and [r[nm:] for r in ext] == [fem["seraphite"], fem["wlf"]],
          f"ext female rows == dc_data_patches.FEMALE_LOOKS ({[r[nm:] for r in ext]})")
    check(all(len(r) == n for r in ext) and nm == N and n == nm + len(fem["wlf"]) == nm + len(fem["seraphite"]),
          f"FL_N = {n} look slots per faction ({nm} male + female)")
    winmm_default = ["scar-male-13", "militia-male-11-backpack"]
    check(ext and [r[0] for r in ext] == winmm_default, "pool idx 0 = winmm's own default look per team")

def scen_female_pool():
    """fl_core_set_pool: the default pick range is the male pool (every earlier build), 'always female' only the female rows,
    'mixed' all of them; teammates still differ inside the 2-look female pool, a pool change re-picks an out-of-range next."""
    NF = 8
    c = Core(0, 7)
    L.fl_core_set_team(c.p, 1)
    seen = set()
    for i in range(300):
        L.fl_core_own_spawn(c.p, 1, 10000 + 2000 * i)
        seen.add(c.g(1))
        assert c.g(2) < NF
    check(seen == set(range(N)), f"default pool: 300 lives use exactly the male looks {sorted(seen)}")
    check(L.fl_core_set_pool(c.p, N, NF) == 1 and c.g(2) >= N, "set_pool(female only) re-picks a male coming life")
    seen = set()
    for i in range(300):
        L.fl_core_own_spawn(c.p, 1, 2000000 + 2000 * i)
        seen.add(c.g(1))
    check(seen == {N, N + 1}, f"always female: lives use only the female rows {sorted(seen)}")
    check(L.fl_core_set_pool(c.p, N, NF) == 0, "set_pool with the same range is a no-op")
    check(L.fl_core_set_pool(c.p, 0, NF) == 1, "set_pool(mixed)")
    seen, fem = set(), 0
    for i in range(800):
        L.fl_core_own_spawn(c.p, 1, 5000000 + 2000 * i)
        seen.add(c.g(1)); fem += c.g(1) >= N
    check(seen == set(range(NF)) and 0.15 < fem / 800 < 0.35, f"mixed: all {NF} looks, female share {fem / 800:.2f} (expect 0.25)")
    check(L.fl_core_set_pool(c.p, 5, 5) == 0 and L.fl_core_set_pool(c.p, 0, NF + 1) == 0, "bad ranges are refused")

if __name__ == "__main__":
    scen_pools()
    scen_female_pool()
    scen_old_bug()
    scen_1v1()
    scen_2v2()
    scen_late_join(False)
    scen_late_join(True)
    scen_host_migration()
    scen_session_late()
    print("\n%d failure(s)" % len(FAILS))
    sys.exit(1 if FAILS else 0)
