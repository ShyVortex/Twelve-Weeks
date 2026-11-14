"""Offline tests for the admin control (daemon live_snapshot / admin_kick / the loopback HTTP listener).
Stuck players (queued, in a not-yet-launched match, in a running match, in a finished-but-held match) are kicked and must be able to queue again.
Run: python tools/tests/test_admin_kick.py   (one loopback listener on a scratch port, temp DB)."""
import hashlib, json, os, sys, tempfile, threading, time, urllib.request, urllib.error
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve"]
T = [tok(n) for n in NAMES]
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2", T2R_QUEUE_SETTLE="0",
                  T2R_FILL_WAIT="0", T2R_MAP_VOTE="0", T2R_P2P="0", T2R_DB=os.path.join(tmp, "t2r.db"), T2R_ADMIN_PORT="17031")
import daemon  # noqa: E402
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
MM = daemon.MM
def pid(t): return hashlib.sha256(t.encode()).hexdigest()[:12]
def reset():
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "late_bonus", "late_mult", "ended_at"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.departed_vol.clear(); daemon.LOADED.clear()
for t in T: daemon.PRES.touch(t, "x")

# --- live snapshot: names, states, no tokens
reset()
now = time.time()
MM.queue[T[0]] = now - 5
MM.matches["m1"] = [T[1], T[2]]; MM.formed["m1"] = now - 30; MM.launched.add("m1"); MM.started.add("m1")
snap = daemon.live_snapshot()
st = {p["name"]: p["state"] for p in snap["players"]}
check(st.get("Alice") == "queue" and st.get("Bob") == "match" and st.get("Dave") == "menu", "live snapshot: queue / match / menu states (%s)" % st)
check(snap["matches"] and snap["matches"][0]["state"] == "running" and len(snap["matches"][0]["players"]) == 2, "live snapshot: the running match with its 2 players")
check(all(t not in json.dumps(snap) for t in T), "live snapshot holds no token")

# --- kick: queued
reset(); MM.queue[T[0]] = time.time(); MM.seen[T[0]] = time.time()
r = daemon.admin_kick(pid(T[0]))
check(r["ok"] and T[0] not in MM.queue and "queue" in r["did"], "kick removes a queued player")
check(T[0] not in daemon.PRES.players, "kick drops presence (it re-registers with its next keepalive)")
daemon.PRES.touch(T[0], "x")
daemon.MM.enqueue(T[0]); check(T[0] in MM.queue, "the kicked player can queue again")

# --- kick: in a match that never launched -> called off, the other goes back to the queue
reset(); MM.matches["m2"] = [T[0], T[1]]; MM.formed["m2"] = time.time(); MM.qtime["m2"] = {T[0]: time.time(), T[1]: time.time()}
daemon.LOADED.add(T[0])
r = daemon.admin_kick(pid(T[0]))
check(r["ok"] and "m2" not in MM.matches and T[1] in MM.queue and T[0] not in MM.queue, "pre-launch match called off, the other player searches again")
check(T[0] not in daemon.LOADED and MM.mid_of(T[0]) is None, "LOADED cleared, no match membership")

# --- kick: stuck in a RUNNING match (a player stuck in the match)
reset(); MM.matches["m3"] = [T[0], T[1], T[2]]; MM.formed["m3"] = time.time() - 60; MM.launched.add("m3"); MM.started.add("m3")
daemon.LOADED.update([T[0], T[1], T[2]])
r = daemon.admin_kick(pid(T[1]))
check(r["ok"] and MM.mid_of(T[1]) is None and not MM.in_match(T[1]), "running match: the player is out of it")
check(MM.mid_of(T[0]) == "m3" and T[1] not in daemon.LOADED, "the others keep the match")
daemon.PRES.touch(T[1], "x"); MM.enqueue(T[1]); check(T[1] in MM.queue, "the kicked player can queue again (not 'already in a match')")

# --- kick: finished match still held
reset(); MM.matches["m4"] = [T[3], T[4]]; MM.formed["m4"] = time.time() - 900; MM.launched.add("m4"); MM.started.add("m4"); MM.ended.add("m4")
r = daemon.admin_kick(pid(T[3]))
check(r["ok"] and T[3] in MM.departed.get("m4", ()) and MM.mid_of(T[3]) is None, "finished-held match: stepped out")

# --- bad input never raises
check(not daemon.admin_kick("zz")["ok"] and not daemon.admin_kick(None)["ok"] and not daemon.admin_kick("ffffffffffff")["ok"], "bad / unknown pid refused")

# --- the loopback listener: secret needed, /status open
threading.Thread(target=daemon.admin_server, daemon=True).start()
time.sleep(0.6)
base = "http://127.0.0.1:17031"
def call(path, data=None, secret=None):
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, method="POST" if data is not None else "GET")
    if secret: req.add_header("X-Admin-Secret", secret)
    try:
        with urllib.request.urlopen(req, timeout=5) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
sec = open(daemon.ADMIN_SECRET_PATH).read().strip()
check(len(sec) == 32, "admin-secret.txt auto-created next to the DB")
check(call("/status")[0] == 200 and "online" in call("/status")[1], "/status open, counts only")
check(call("/live")[0] == 403 and call("/kick", {"pid": "x"})[0] == 403, "/live and /kick refuse without the secret")
check(call("/live", secret="nope")[0] == 403, "wrong secret refused")
reset(); MM.queue[T[2]] = time.time()
c, j = call("/live", secret=sec)
check(c == 200 and any(p["name"] == "Carol" for p in j["live"]["players"]), "/live with the secret")
c, j = call("/kick", {"pid": pid(T[2])}, sec)
check(c == 200 and j["ok"] and T[2] not in MM.queue, "POST /kick with the secret works")

# --- kick reason: notice text, sanitising, delivery on the held socket (0x11 before 0x0d) and via the notice poll
check(daemon.kick_text("") == "You got kicked from the match." and daemon.kick_text(None) == "You got kicked from the match.", "no reason: plain text")
check(daemon.kick_text("  cheating \x00\n\t now ") == 'You got kicked from the match. Reason: "cheating now"', "reason trimmed, control chars stripped")
check(len(daemon.kick_reason_clean("x" * 500)) == 120, "reason capped at 120")
class FakeConn:
    def __init__(self): self.buf = b""
    def sendall(self, b): self.buf += b
reset(); fc = FakeConn()
daemon.SESSIONS.conn = lambda t: fc if t == T[4] else None
daemon.SESSIONS.unregister = lambda t, c: None
r = daemon.admin_kick(pid(T[4]), "  griefing ")
exp = daemon.msg(0x11, b'You got kicked from the match. Reason: "griefing"') + daemon.msg(0x0d, b"\x01")
check(r["ok"] and fc.buf == exp, "kick with reason: 0x11 note then 0x0d on the session socket")
lines = [x[3] for x in daemon.SOCIAL.notes_for(T[4])]
check(lines == ['You got kicked from the match. Reason: "griefing"'], "kick with reason: notice-poll line (%s)" % lines)
fc = FakeConn(); daemon.PRES.touch(T[4], "x")
r = daemon.admin_kick(pid(T[4]))
check(r["ok"] and fc.buf == daemon.msg(0x11, b"You got kicked from the match.") + daemon.msg(0x0d, b"\x01"), "kick without reason: plain text, old call signature still works")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
