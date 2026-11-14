"""Per-stage wall-time profile for build_dll.py (printed as a sorted table at the end of a build).

  buildprof.lap("name")      closes the segment since the previous lap/mark and books it under `name`
  with buildprof.stage("n"): books the block's wall time under `n` (nestable; nested time is also counted in the outer lap,
                             so only `lap` totals add up to the build time - `stage` rows are listed separately)
  buildprof.report()         sorted table; also appended to tools/local/build_profile.log
"""
import contextlib
import time

_t0 = time.perf_counter()
_last = _t0
_laps = {}
_stages = {}


def reset():
    global _t0, _last
    _t0 = _last = time.perf_counter()
    _laps.clear()
    _stages.clear()
    _steps.clear()


def lap(name):
    global _last
    now = time.perf_counter()
    _laps[name] = _laps.get(name, 0.0) + (now - _last)
    print(f"STEP {name} {now - _last:.1f} s (ran)", flush=True)
    _last = now


@contextlib.contextmanager
def stage(name):
    t = time.perf_counter()
    try:
        yield
    finally:
        dt = time.perf_counter() - t
        _stages[name] = _stages.get(name, 0.0) + dt
        print(f"STEP ~{name} {dt:.1f} s (ran)", flush=True)


_steps = []          # (name, seconds, "cached"|"ran") of every cached/verified step, see note_step


def note_step(name, secs, how):
    """buildcache calls this for every cached()/verified() step; prints one STEP line"""
    _steps.append((name, secs, how))
    print(f"STEP {name} {secs:.1f} s ({how})", flush=True)


def report(path=None, extra=()):
    lap("(tail)")
    total = time.perf_counter() - _t0
    rows = sorted(_laps.items(), key=lambda kv: -kv[1])
    lines = [f"{'stage':64s} {'sec':>8s} {'%':>6s}"]
    for n, s in rows:
        lines.append(f"{n[:64]:64s} {s:8.1f} {100 * s / total:5.1f}%")
    if _stages:
        lines.append("-- nested stages (already inside the laps above) --")
        for n, s in sorted(_stages.items(), key=lambda kv: -kv[1]):
            lines.append(f"~{n[:63]:63s} {s:8.1f} {100 * s / total:5.1f}%")
    lines.extend(extra)
    allrows = [(n, s, "ran") for n, s in _laps.items()] + [("~" + n, s, "ran") for n, s in _stages.items()] + _steps
    lines.append("-- 15 slowest steps (top-level laps, nested stages ~, cached/verified steps) --")
    for n, s, how in sorted(allrows, key=lambda r: -r[1])[:15]:
        lines.append(f"{n[:56]:56s} {s:8.1f} ({how})")
    lines.append(f"{'TOTAL':64s} {total:8.1f}")
    text = "\n".join(lines)
    print("\n=== build profile ===\n" + text)
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(time.strftime("\n--- %Y-%m-%d %H:%M:%S ---\n") + text + "\n")
        except OSError:
            pass
    return total
