"""Server db power-loss guard: verified backup, zeroed / truncated t2r.db restored at start (daemon.db_guard / db_backup)."""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import daemon

fails = 0
def check(name, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + name)
    fails += 0 if ok else 1

d = tempfile.mkdtemp()
daemon.DB_PATH = os.path.join(d, "t.db"); daemon.BAK_PATH = daemon.DB_PATH + ".bak"
tok = "ab" * 32
check("no db yet", daemon.db_guard() == "no db yet")
daemon.set_name(tok, "bob")
check("healthy db ok", daemon.db_guard() == "ok")
check("backup written", daemon.db_backup() and os.path.exists(daemon.BAK_PATH) and not os.path.exists(daemon.BAK_PATH + ".tmp"))
for label, junk in (("emptied", b""), ("zero-filled", b"\0" * 8192), ("garbage", b"x" * 5000)):
    open(daemon.DB_PATH, "wb").write(junk)
    check(label + " db is not backed up over the good backup", not daemon.db_backup() and daemon._db_ok(daemon.BAK_PATH))
    check(label + " db restored", daemon.db_guard().startswith("CORRUPT - restored") and daemon.get_name(tok) == "bob")
print("\n%d failure(s)" % fails)
sys.exit(1 if fails else 0)
