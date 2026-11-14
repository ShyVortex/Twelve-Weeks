"""Release host folder: build_release.HOST_FILES must hold everything daemon.py imports (gunlimit.py was once missing and the
server did not start). Run: python tools/tests/test_release_host.py   (plain python; copies into a temp folder, imports the daemon with a temp DB)."""
import importlib.util, os, shutil, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
spec = importlib.util.spec_from_file_location("build_release", os.path.join(ROOT, "release", "build_release.py"))
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)          # (module level only defines things; main() is not called)

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

for f in [f for f in br.HOST_FILES if f not in br.OPTIONAL_HOST_FILES]:
    check(os.path.exists(os.path.join(TOOLS, f)), "HOST_FILES: tools/%s exists" % f)
with tempfile.TemporaryDirectory() as td:
    host = os.path.join(td, "host")
    os.makedirs(host)
    for f in br.HOST_FILES:
        if os.path.exists(os.path.join(TOOLS, f)):
            shutil.copy(os.path.join(TOOLS, f), host)
    try:
        br.check_host(host)
        check(True, "daemon.py imports from a folder holding exactly HOST_FILES")
    except SystemExit as e:
        check(False, "daemon.py imports from the host folder: %s" % e)
    # negative control: without gunlimit.py the check must fail
    os.remove(os.path.join(host, "gunlimit.py"))
    try:
        br.check_host(host)
        check(False, "check_host fails when a module is missing")
    except SystemExit:
        check(True, "check_host fails when a module is missing")
# the clan feed modules are optional in the daemon (silently absent): they must still ship, or the clan feed is empty
check(all(m in br.HOST_FILES for m in ("clan_story.py", "clan_story_data.py", "clan_story_lines_good.py", "clan_story_lines_dark.py",
                                                                    "clan_story_pl.py", "clan_story_pl_good.py", "clan_story_pl_dark.py")), "clan feed modules ship")
# the whole import graph of daemon.py (also imports inside functions and optional try/except imports): every tools/*.py module it reaches must ship, or an
# optional feature (the clan chronicle / saga / supply feed) silently turns off on the live host
import ast
def _imports(f):
    t = ast.parse(open(os.path.join(TOOLS, f), encoding="utf-8").read())
    mods = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    return {m + ".py" for m in mods if os.path.exists(os.path.join(TOOLS, m + ".py"))}
_seen, _todo = set(), ["daemon.py"]
while _todo:
    _f = _todo.pop()
    if _f not in _seen:
        _seen.add(_f)
        _todo += list(_imports(_f))
_missing = sorted(m for m in _seen if m not in br.HOST_FILES)
check(not _missing, "every tools/*.py module in daemon.py's import graph is in HOST_FILES (%d modules)%s" % (len(_seen), "; missing: " + ", ".join(_missing) if _missing else ""))
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
