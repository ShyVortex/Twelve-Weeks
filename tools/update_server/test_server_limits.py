"""Long-uptime limits of the update server (soak audit): per-address report limiter forgets quiet addresses, bigger accept backlog, request idle timeout.
Run: python tools/update_server/test_server_limits.py"""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_store, server  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

now = [1000.0]
L = report_store.RateLimiter(n=3, window=60.0, clock=lambda: now[0])
for i in range(3000):
    L.allow("10.0.%d.%d" % (i // 250, i % 250))
check(len(L.hits) == 3000, "3000 addresses tracked inside the window")
now[0] += 120
L.allow("1.1.1.1")
check(len(L.hits) < 10, "quiet addresses are dropped once the table is large (%d left)" % len(L.hits))
check([L.allow("2.2.2.2") for _ in range(4)] == [True, True, True, False], "the limit itself is unchanged")

d = tempfile.mkdtemp()
srv = server.make_server(d, "127.0.0.1", 0)
check(srv.request_queue_size >= 128, "accept backlog is %d (socketserver default: 5)" % srv.request_queue_size)
H = srv.RequestHandlerClass
check(H.timeout and H.timeout <= 60, "request handlers have an idle timeout (%s s)" % H.timeout)
srv.server_close()
print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
