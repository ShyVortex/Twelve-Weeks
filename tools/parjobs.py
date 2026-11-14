"""Run independent build jobs in child interpreters (no multiprocessing/spawn: the parent is often a runpy'd build_dll whose
__main__ must not be re-imported).

  results = parjobs.run([(module, func, args, kwargs), ...], workers=None)   -> [return value of each job, in job order]

A job is `module.func(*args, **kwargs)` with the module found through the parent's sys.path.  Each child gets the parent's environment and
sys.path, its stdout is captured and replayed by the parent in JOB ORDER (the log reads like the serial run), a failing child raises
RuntimeError with its output.  workers = T2R_PAR_JOBS or min(cpu_count - 2, 6); 1 (or a single job) runs the jobs in-process in order, which is
the serial reference: results must not depend on the worker count (T2R_PAR_JOBS=1 to compare)."""
import os
import pickle
import subprocess
import sys
import tempfile
import threading


NEED_COMMIT_GB = float(os.environ.get("T2R_PAR_CHILD_GB", "2.5"))      # commit charge one child may need (level_edit children peak at 1.6-1.9 GB)


def free_commit_gb():
    """available commit charge (physical + page file) in GB; None where it cannot be read"""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return None
        return m.ullAvailPageFile / 2 ** 30
    except Exception:
        return None


def workers_default(cap=6):
    v = os.environ.get("T2R_PAR_JOBS")
    if v:
        return max(1, int(v))
    w = max(1, min((os.cpu_count() or 4) - 2, cap))
    f = free_commit_gb()
    if f is not None:                       # never more children than the free commit charge can hold (night56: commit ran out, 0xC0000142)
        w = max(1, min(w, int(f / NEED_COMMIT_GB)))
    return w


def _child(jobfile):
    with open(jobfile, "rb") as f:
        paths, mod, func, args, kwargs = pickle.load(f)
    sys.path[:0] = [p for p in paths if p not in sys.path]
    import importlib
    try:
        res = (True, getattr(importlib.import_module(mod), func)(*args, **kwargs))
    except BaseException as e:           # SystemExit from a failed build check must reach the parent too
        import traceback
        traceback.print_exc()
        res = (False, repr(e))
    sys.stdout.flush()
    with open(jobfile + ".res", "wb") as f:
        pickle.dump(res, f)


_adm = threading.Condition()
_running = [0]


def _admit():
    """start a child only when the free commit charge holds it (or nothing of ours is running: then it must go ahead anyway)"""
    with _adm:
        while True:
            f = free_commit_gb()
            if _running[0] == 0 or f is None or f >= NEED_COMMIT_GB + 0.5:
                _running[0] += 1
                return
            _adm.wait(3)


def _release():
    with _adm:
        _running[0] -= 1
        _adm.notify_all()


def run(jobs, workers=None, log=print, child_env=None, force_child=False):
    workers = workers_default() if workers is None else workers
    if not force_child and (workers <= 1 or len(jobs) <= 1):
        out = []
        saved = {k: os.environ.get(k) for k in (child_env or {})}
        os.environ.update(child_env or {})
        try:
            for mod, func, args, kwargs in jobs:
                import importlib
                out.append(getattr(importlib.import_module(mod), func)(*args, **kwargs))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        return out
    tmp = tempfile.mkdtemp(prefix="t2r-par-")
    slots = threading.Semaphore(workers)
    results = [None] * len(jobs)
    outputs = [""] * len(jobs)
    retry = []

    def go(i):
        mod, func, args, kwargs = jobs[i]
        jf = os.path.join(tmp, f"job{i}.pkl")
        with open(jf, "wb") as f:
            pickle.dump((list(sys.path), mod, func, args, kwargs), f)
        with slots:
            _admit()
            try:
                p = subprocess.run([sys.executable, "-u", os.path.abspath(__file__), "--child", jf], capture_output=True,
                                   env=dict(os.environ, **child_env) if child_env else None)
            finally:
                _release()
        outputs[i] = (p.stdout + p.stderr).decode(errors="replace")
        try:
            with open(jf + ".res", "rb") as f:
                results[i] = pickle.load(f)
        except OSError:
            results[i] = (False, f"child exited {p.returncode} without a result")
            if p.returncode in (0xC0000142, -1073741502, 0xC0000005, -1073741819, 0xC000012D, -1073741523) or (p.returncode and p.returncode < 0):
                retry.append(i)              # out of memory / process start failure: run it again alone after the pool
    ts = [threading.Thread(target=go, args=(i,)) for i in range(len(jobs))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    for i in sorted(retry):                  # a child that died of a start / memory failure (0xC0000142 ...): again, one at a time, nothing else running
        for attempt in range(2):
            print(f"parjobs: job {i} {jobs[i][:2]} died ({outputs[i][-80:].strip() or results[i][1]}): retrying alone")
            jf = os.path.join(tmp, f"job{i}.pkl")
            if os.path.exists(jf + ".res"):
                os.remove(jf + ".res")
            p = subprocess.run([sys.executable, "-u", os.path.abspath(__file__), "--child", jf], capture_output=True, env=dict(os.environ, **child_env) if child_env else None)
            outputs[i] = (p.stdout + p.stderr).decode(errors="replace")
            try:
                with open(jf + ".res", "rb") as f:
                    results[i] = pickle.load(f)
                break
            except OSError:
                results[i] = (False, f"child exited {p.returncode} without a result")
    bad = None
    for i, (ok, val) in enumerate(results):
        if outputs[i]:
            log(outputs[i].rstrip("\n"))
        if not ok and bad is None:
            bad = (i, val)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        raise RuntimeError(f"parallel job {jobs[bad[0]][:2]} failed: {bad[1]}")
    return [v for _ok, v in results]


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--child":
    _child(sys.argv[2])
