"""Unit tests for the daemon log handling (soak audit): per-category rate limit of log(), capped stats lines, T2R_LOG_PATH, rotation.
Run: python tools/tests/test_daemon_log_limit.py   (temp files, no ports)."""
import os, sys, socket, subprocess, tempfile, time, collections
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_DB=os.path.join(tmp, "t2r.db"))
import daemon  # noqa: E402

def drain():
    out = []
    while daemon._q:
        out.append(daemon._q.popleft())
    return out

# ------------------------------------------------------------------ per-category limiter
drain()
daemon.LOG_BURST, daemon.LOG_PER_S = 20, 1.0
daemon._log_cat.clear()
for i in range(500):
    daemon.log("TCP", ("1.2.3.4", i), "recv 12B")
lines = drain()
check(20 <= len(lines) <= 22, "a per-packet category is cut to its burst (%d of 500 lines written)" % len(lines))
for i in range(5):
    daemon.log("UDP", "other category", i)
check(len(drain()) == 5, "another category is unaffected by the flood of the first")
daemon.log("STATUS", "online=1")
for i in range(300):
    daemon.log("STATUS", "online=%d" % i)
check(len(drain()) == 301, "STATUS lines are never limited")
# EVT kinds are separate categories
for i in range(30):
    daemon.evt("queue", "x", i)
    daemon.evt("loaded", "y", i)
lines = drain()
check(sum("EVT queue" in l for l in lines) == 20 and sum("EVT loaded" in l for l in lines) == 20, "EVT lines are limited per kind (a queue flood does not hide 'loaded')")
# one summary line per 5 s window
b = daemon._log_cat["TCP"]
b[3] -= 10.0                                   # last summary was long ago
daemon.log("TCP", "one more")
lines = drain()
check(any("LOG-SUPPRESSED TCP" in l for l in lines), "the suppressed lines are summarised: %s" % [l for l in lines if "SUPPRESSED" in l])
n = sum(1 for _ in range(10) if daemon.log("TCP", "again") is None)
check(not any("SUPPRESSED" in l for l in drain()), "no second summary inside the 5 s window")
# refill: after a pause the category may speak again
daemon.LOG_BURST, daemon.LOG_PER_S = 5, 100.0
daemon._log_cat.clear()
for i in range(5): daemon.log("REFILL", i)
daemon.log("REFILL", "dropped")
drain()
time.sleep(0.1)
daemon.log("REFILL", "back")
check(any("back" in l for l in drain()), "tokens refill with time")
# category memory is bounded
daemon.LOG_BURST, daemon.LOG_PER_S = 200, 40.0
daemon._log_cat.clear()
for i in range(1000):
    daemon.log("CAT%d" % i, "x")
check(len(daemon._log_cat) <= 260 and len(drain()) == 1000, "at most ~256 categories are tracked; others are simply not limited (%d tracked)" % len(daemon._log_cat))
# control characters / newlines still neutralised
daemon.log("TCP", "a\nb\rc")
check(drain()[-1].count("\n") == 0, "log() still strips newlines from player-supplied text")
# non-str first argument
daemon.log(("x", 1), "y")
daemon.log()
check(len(drain()) == 2, "log() with odd arguments does not raise")

# ------------------------------------------------------------------ stats lines
c = collections.Counter({(("10.0.0.%d" % (i % 250), 1000 + i), 3): i + 1 for i in range(5000)})
snap = daemon._take(c)
check(not c and len(snap) == 5000 and snap[0][1] == 5000 and snap[-1][1] == 1, "_take: snapshot sorted biggest first, counter cleared")
line = " | ".join("%s:%d" % (a, n) for a, n in snap[:daemon.STATS_LINES])
check(len(line) < 2000, "a status stats line shows at most %d entries (%d chars for 5000 sources)" % (daemon.STATS_LINES, len(line)))

# ------------------------------------------------------------------ T2R_LOG_PATH + rotation
lp = os.path.join(tmp, "custom", "x.log")
os.makedirs(os.path.dirname(lp))
env = dict(os.environ, T2R_LOG_PATH=lp)
r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import daemon; print(daemon.LOG_PATH)" % TOOLS], capture_output=True, text=True, env=env, timeout=60)
check(r.stdout.strip().splitlines()[-1] == lp, "T2R_LOG_PATH moves the log: %s" % r.stdout.strip()[-80:])
r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import daemon; print(daemon.LOG_PATH)" % TOOLS], capture_output=True, text=True,
                   env={k: v for k, v in os.environ.items() if k != "T2R_LOG_PATH"}, timeout=60)
check(r.stdout.strip().splitlines()[-1].endswith(os.path.join("tools", "daemon.log")), "default log path unchanged")

# the flusher keeps the log under LOG_MAX_BYTES * (LOG_KEEP + 1): run it for real with a tiny cap
daemon.LOG_PATH = os.path.join(tmp, "rot.log")
daemon.LOG_MAX_BYTES, daemon.LOG_KEEP = 20000, 2
daemon.LOG_BURST, daemon.LOG_PER_S = 10 ** 9, 10 ** 9      # the limiter is not what is tested here
import threading
t = threading.Thread(target=daemon._flusher, daemon=True); t.start()
time.sleep(0.3)
for i in range(3000):
    daemon.log("ROT", "line %d" % i, "x" * 40)
    if i % 500 == 0: time.sleep(0.6)
time.sleep(1.2)
files = [f for f in os.listdir(tmp) if f.startswith("rot.log")]
total = sum(os.path.getsize(os.path.join(tmp, f)) for f in files)
check(len(files) == 3 and total < 20000 * 3 + 600, "rotation keeps LOG_KEEP+1 files within the cap (%s, %d bytes)" % (sorted(files), total))
check(os.path.exists(daemon.LOG_PATH) and "ROT line 2999" in open(daemon.LOG_PATH, encoding="utf-8").read(), "the newest lines are in the live file")

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
