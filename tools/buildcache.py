"""Content-hash cache for the expensive, deterministic steps of the data build (tools/features/build_dll.py).

A step's key = sha1 of everything that can change its result:
  * the step's code: its module plus the transitive closure of the project modules it imports (static `import` scan of the
    repo's tool directories), file contents hashed - editing any module a step uses invalidates it, editing others does not;
  * its inputs: bytes / strings / numbers given by the caller, `Stat(path)` for big input trees (relative path + size + mtime of
    every file below it, so a 5 GB model directory costs milliseconds), `File(path)` for files hashed by content.

Entries live in tools/local/build-cache/steps/<name>/<key>/ (shared by every worktree through the tools/local junction), are
written atomically and touched on every hit; entries unused for CACHE_DAYS are pruned. T2R_NO_BUILD_CACHE=1 turns the whole
thing off (every step runs for real, as before) - use it to prove a cached build equals an uncached one.

  cached(name, parts, fn, files=[abs paths fn writes], dirs=[abs dirs fn fills])   -> fn()'s return value (picklable)
  verified(name, parts, fn)   a pure check (raises / returns False on failure): a pass is remembered, not repeated
"""
import ast
import hashlib
import os
import pickle
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(HERE, "local", "build-cache", "steps")
CACHE_DAYS = 21
DISABLED = bool(os.environ.get("T2R_NO_BUILD_CACHE"))

# where the build's python modules live (a module name is looked up in each; unknown names = stdlib / site-packages, not tracked)
CODE_DIRS = [os.path.join(ROOT, *p.split("/")) for p in (
    "tools", "tools/features", "tools/models", "tools/models/figures", "tools/part1", "tools/maps", "tools/win",
    "re/uc4ps4/tools", "re/factions2013/t1anim")]

stats = {"hit": [], "miss": []}


class Stat(str):
    """a path whose files are keyed by (relative path, size, mtime_ns)"""


class File(str):
    """a file keyed by its content"""


_HASH_DB = os.path.join(HERE, "local", "build-cache", "filehash.json")
_file_hash = {}
_db = None


def _load_db():
    global _db
    if _db is None:
        try:
            import json
            with open(_HASH_DB) as f:
                _db = json.load(f)
        except (OSError, ValueError):
            _db = {}
        import atexit
        atexit.register(_save_db)
    return _db


def _save_db():
    if _db is None or not _db_dirty:
        return
    try:
        import json
        os.makedirs(os.path.dirname(_HASH_DB), exist_ok=True)
        tmp = f"{_HASH_DB}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(_db, f)
        os.replace(tmp, _HASH_DB)
    except OSError:
        pass


_db_dirty = False


def _hash_file(path):
    """sha1 of a file's content; remembered by (path, size, mtime) in a small json db, so a re-run only hashes what changed"""
    global _db_dirty
    try:
        st = os.stat(path)
    except OSError:
        return "missing"
    k = f"{path}|{st.st_size}|{st.st_mtime_ns}"
    if k not in _file_hash:
        db = _load_db()
        if k not in db:
            h = hashlib.sha1()
            with open(path, "rb") as f:
                for blk in iter(lambda: f.read(1 << 22), b""):
                    h.update(blk)
            db[k] = h.hexdigest()
            _db_dirty = True
        _file_hash[k] = db[k]
    return _file_hash[k]


class Hashed(str):
    """every file below this directory (or this one file) keyed by content hash - for data trees that decide a step's output"""


class Content(str):
    """the files directly in this directory matching `pattern` (default *.pak), keyed by content hash - robust against a
    step that rewrites identical bytes (new mtime) or a sibling cache directory that churns"""
    pattern = "*.pak"

    def __new__(cls, path, pattern="*.pak"):
        o = str.__new__(cls, path)
        o.pattern = pattern
        return o


def _module_file(name):
    top = name.split(".")[0]
    for d in CODE_DIRS:
        p = os.path.join(d, top + ".py")
        if os.path.isfile(p):
            return p
        p = os.path.join(d, top, "__init__.py")
        if os.path.isfile(p):
            return p
    return None


_imports = {}


def _imports_of(path):
    if path not in _imports:
        names = set()
        try:
            tree = ast.parse(open(path, "rb").read())
        except (SyntaxError, OSError):
            tree = None
        for n in ast.walk(tree) if tree else ():
            if isinstance(n, ast.Import):
                names.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                if n.module:
                    names.add(n.module)
                    names.update(f"{n.module}.{a.name}" for a in n.names)
                else:
                    names.update(a.name for a in n.names)       # from . import x
        _imports[path] = names
    return _imports[path]


_closure = {}


def code_files(*modules):
    """absolute paths of the modules (names or .py paths) and every project module they import, transitively"""
    key = tuple(modules)
    if key in _closure:
        return _closure[key]
    todo = []
    for m in modules:
        p = m if m.endswith(".py") else _module_file(m)
        if p is None:
            raise KeyError(f"buildcache: module {m} not found in the project directories")
        todo.append(os.path.abspath(p))
    seen = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        for n in _imports_of(p):
            q = _module_file(n)
            if q and os.path.abspath(q) not in seen:
                todo.append(os.path.abspath(q))
    _closure[key] = sorted(seen)
    return _closure[key]


def env_names(*modules):
    """the T2R_* switch names mentioned in the source of these modules + their project imports"""
    import re
    return {m.decode() for m in re.findall(rb"T2R_[A-Z0-9_]+", _sources(code_files(*modules)))}


class Code(tuple):
    """the code of these modules (+ their project imports)"""
    skip_data = ()

    def __new__(cls, *modules, skip_data=()):
        o = tuple.__new__(cls, modules)
        o.skip_data = tuple(skip_data)       # data file names next to the code the caller keys itself (finer than the whole file)
        return o


_VOLATILE = (".py", ".pyc", ".db", ".log", ".stdout", ".stderr", ".sh", ".md", ".MD", ".ps1", ".bat", ".tmp")
_src_cache = {}


def _sources(files):
    """the concatenated text of the closure's .py files (what a data file's name is searched in)"""
    k = tuple(files)
    if k not in _src_cache:
        _src_cache[k] = b"\n".join(open(f, "rb").read() for f in files)
    return _src_cache[k]


def _feed(h, p):
    if isinstance(p, Code):
        files = code_files(*p)
        for f in files:
            h.update(b"C" + os.path.relpath(f, ROOT).encode() + b"\0" + _hash_file(f).encode())
        src = _sources(files)
        for d in sorted({os.path.dirname(f) for f in files}):           # data files that sit next to the code (txt / json / npz ...)
            for n in sorted(os.listdir(d)):
                q = os.path.join(d, n)
                # only files the closure's source names (a file the code reads has its name or stem in the text); runtime churn
                # in the same directories (t2r.db, logs, *.stdout, scripts, readmes) must not invalidate model / clip builds
                if (os.path.isfile(q) and not n.endswith(_VOLATILE) and n not in p.skip_data
                        and (n.encode() in src or os.path.splitext(n)[0].encode() in src)):
                    h.update(b"D" + os.path.relpath(q, ROOT).encode() + b"\0" + _hash_file(q).encode())
    elif isinstance(p, Hashed):
        base = str(p)
        h.update(b"H")
        if os.path.isfile(base):
            h.update(_hash_file(base).encode())
        else:
            for r, ds, fs in os.walk(base):
                ds[:] = sorted(d for d in ds if d != "__pycache__")
                for f in sorted(fs):
                    q = os.path.join(r, f)
                    h.update(os.path.relpath(q, base).encode() + b"=" + _hash_file(q).encode() + b";")
    elif isinstance(p, Content):
        import fnmatch
        h.update(b"N")
        for f in sorted(os.listdir(str(p))):
            q = os.path.join(str(p), f)
            if fnmatch.fnmatch(f, p.pattern) and os.path.isfile(q):
                h.update(f.encode() + b"=" + _hash_file(q).encode() + b";")
    elif isinstance(p, File):
        h.update(b"F" + _hash_file(str(p)).encode())
    elif isinstance(p, Stat):
        base = str(p)
        if os.path.realpath(base).startswith(os.path.realpath(ROOT) + os.sep):
            # inside this checkout (git-tracked trees like re/uc4ps4): a fresh worktree's checkout mtimes must not change the key, so by content
            return _feed(h, Hashed(base))
        h.update(b"S")
        if os.path.isfile(base):
            st = os.stat(base)
            h.update(f"{os.path.basename(base)}:{st.st_size}:{st.st_mtime_ns}".encode())
        else:
            rows = []
            for r, ds, fs in os.walk(base):
                ds[:] = [d for d in ds if d != "__pycache__"]
                for f in fs:
                    q = os.path.join(r, f)
                    try:
                        st = os.stat(q)
                    except OSError:
                        continue
                    rows.append(f"{os.path.relpath(q, base)}:{st.st_size}:{st.st_mtime_ns}")
            h.update("\n".join(sorted(rows)).encode())
    elif isinstance(p, (bytes, bytearray, memoryview)):
        h.update(b"B%d:" % len(p))
        h.update(p)
    elif isinstance(p, str):
        h.update(b"s" + p.encode())
    elif isinstance(p, dict):
        for k in sorted(p, key=repr):
            h.update(b"k")
            _feed(h, k)
            _feed(h, p[k])
    elif isinstance(p, (list, tuple, set, frozenset)):
        h.update(b"[")
        for x in (sorted(p, key=repr) if isinstance(p, (set, frozenset)) else p):
            _feed(h, x)
        h.update(b"]")
    else:
        h.update(b"r" + repr(p).encode())
    h.update(b"|")


def key(*parts):
    h = hashlib.sha1()
    for p in parts:
        _feed(h, p)
        if os.environ.get("T2R_CACHE_DEBUG"):             # which part of a key moved between two runs
            hh = hashlib.sha1()
            _feed(hh, p)
            print(f"  cache key part {hh.hexdigest()[:8]}: {str(p)[:100]!r}")
    return h.hexdigest()[:24]


def _atomic_dir(final, fill):
    tmp = f"{final}.tmp{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    fill(tmp)
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp, final)


def _note(name, secs, how):
    try:
        import buildprof
        buildprof.note_step(name, secs, how)
    except Exception:
        print(f"STEP {name} {secs:.1f} s ({how})")


def cached(name, parts, fn, files=(), dirs=()):
    """Run fn() unless an entry for (name, parts) holds its result: `files` (absolute paths fn writes) and `dirs` (absolute
    directories fn fills) are restored from the entry, fn's return value comes from a pickle. Nothing is cached if fn raises
    or its result cannot be pickled."""
    if DISABLED:
        return fn()
    k = key(name, *parts)
    entry = os.path.join(CACHE_DIR, name, k)
    t0 = time.perf_counter()
    if os.path.isfile(os.path.join(entry, "ok")):
        try:
            for i, f in enumerate(files):
                os.makedirs(os.path.dirname(f), exist_ok=True)
                shutil.copyfile(os.path.join(entry, f"f{i}"), f)
            for i, d in enumerate(dirs):
                shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(os.path.join(entry, f"d{i}"), d)
            with open(os.path.join(entry, "ret.pkl"), "rb") as fh:
                ret = pickle.load(fh)
            os.utime(os.path.join(entry, "ok"), None)
            stats["hit"].append((name, time.perf_counter() - t0))
            _note(name, time.perf_counter() - t0, "cached")
            print(f"build cache: {name} - hit ({k})")
            return ret
        except Exception as e:                      # a damaged entry: build for real
            print(f"build cache: {name} - entry unusable ({e}), rebuilding")
    ret = fn()
    t1 = time.perf_counter()
    try:
        blob = pickle.dumps(ret)

        def fill(tmp):
            for i, f in enumerate(files):
                shutil.copyfile(f, os.path.join(tmp, f"f{i}"))
            for i, d in enumerate(dirs):
                shutil.copytree(d, os.path.join(tmp, f"d{i}"))
            with open(os.path.join(tmp, "ret.pkl"), "wb") as fh:
                fh.write(blob)
            open(os.path.join(tmp, "ok"), "w").write("ok")
        _atomic_dir(entry, fill)
    except Exception as e:
        print(f"build cache: {name} - not stored ({e})")
    stats["miss"].append((name, t1 - t0))
    _note(name, t1 - t0, "ran")
    print(f"build cache: {name} - built ({k})")
    return ret


def verified(name, parts, fn):
    """A pure check (raises, or returns False, when it fails): once it passed for these parts, later builds skip it"""
    if DISABLED:
        return fn()
    k = key("verified", name, *parts)
    marker = os.path.join(CACHE_DIR, "verify-" + name, k, "ok")
    if os.path.isfile(marker):
        os.utime(marker, None)
        stats["hit"].append(("verify " + name, 0.0))
        _note("verify " + name, 0.0, "cached")
        print(f"build cache: verify {name} - passed before ({k})")
        return True
    t0 = time.perf_counter()
    res = fn()
    if res is not False:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, "w").write("ok")
    stats["miss"].append(("verify " + name, time.perf_counter() - t0))
    _note("verify " + name, time.perf_counter() - t0, "ran")
    return res


def prune(days=CACHE_DAYS):
    """drop entries nobody used for a while (hits refresh the mtime of the entry's `ok` marker)"""
    old = time.time() - days * 86400
    try:
        for name in os.listdir(CACHE_DIR):
            nd = os.path.join(CACHE_DIR, name)
            for e in os.listdir(nd):
                p = os.path.join(nd, e)
                ok = os.path.join(p, "ok")
                t = os.stat(ok if os.path.isfile(ok) else p).st_mtime
                if t < old:
                    shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    except OSError:
        pass
