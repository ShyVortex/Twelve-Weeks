"""Smoke test of the soak harness itself (tools/tests/soak_daemon.py --quick): a real daemon process, 8 fake clients + the chaos thread for ~25 s.
It must start, match the clients, stay alive, answer the probe poll and keep its log under the cap. (The trend verdicts need minutes: see
re/daemon-soak-1019.md for the 10-minute / 50-client numbers.)  Run: python tools/tests/test_soak_harness.py"""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import soak_daemon  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

# trend helper: flat / growing series
flat = [50.0 + (i % 3) * 0.1 for i in range(60)]
grow = [50.0 + i * 0.5 for i in range(60)]
check(not soak_daemon.trend(flat, 0.08, 1.0)[3], "trend(): a flat series is fine")
check(soak_daemon.trend(grow, 0.08, 1.0)[3], "trend(): a steadily growing series is flagged")
check(not soak_daemon.trend([1, 2, 3], 0.08, 1.0)[3], "trend(): too few samples = no verdict")
check(soak_daemon.read_frames(b"\x02\x00\x04\x01\x00\x00\x03\x00\x09")[0] == [(4, b"\x01")], "read_frames(): zero length skipped, complete frame returned, partial kept")

work = tempfile.mkdtemp()
res = soak_daemon.run_soak(0.4, 8, 2.0, work, None, verbose=False, trends=False)
v = res["verdict"]
check(res["ok"], "quick soak passes: %s" % (res["fails"],))
check(v["client_counters"].get("match-start", 0) >= 4, "the fake clients formed matches (%s)" % v["client_counters"].get("match-start"))
check(v["probe_fail"] == 0 and v.get("probe_ms", {}).get("p99", 1e9) < 1500, "probe polls answered: %s" % (v.get("probe_ms"),))
check(len(res["samples"]) >= 6 and res["samples"][-1]["rss_mb"] > 5, "process metrics sampled (%d samples, %.0f MB)" % (len(res["samples"]), res["samples"][-1]["rss_mb"]))
check("Presence.players" in res["samples"][-1]["sizes"], "the daemon's /sizes endpoint is read")

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
