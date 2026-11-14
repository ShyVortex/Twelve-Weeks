"""Unit tests for the daemon database handling under long uptime (soak audit): cached schema check + indexes, connections always closed,
shown-name cache + invalidation, cached searching frame, backup while writing, VACUUM upkeep, new-identity limits on row-creating ops.
Run: python tools/tests/test_daemon_db_soak.py   (temp DB, no ports)."""
import os, sys, socket, sqlite3, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_NAME_CACHE_S="30", T2R_SEARCH_CACHE_S="30")
import daemon  # noqa: E402
tmp = tempfile.mkdtemp()
daemon.DB_PATH = os.path.join(tmp, "t2r.db")
daemon.BAK_PATH = daemon.DB_PATH + ".bak"

def tok(n):
    return ("%08x" % n) * 8

# ------------------------------------------------------------------ connection counting wrapper
real_connect = sqlite3.connect
stmts = []; conns = []
def counting_connect(*a, **k):
    c = real_connect(*a, **k)
    conns.append(c)
    c.set_trace_callback(lambda q: stmts.append(q))
    return c
daemon.sqlite3.connect = counting_connect      # (the module object is shared: restored below)

try:
    # ---------------------------------------------------------------- schema cache + indexes
    daemon.db().close()
    first = [q for q in stmts if "CREATE" in q or "table_info" in q]
    stmts.clear()
    daemon.db().close()
    again = [q for q in stmts if "CREATE" in q or "table_info" in q]
    check(len(first) >= 5 and not again, "the schema is verified once per database file, not on every call (%d statements first, %d after)" % (len(first), len(again)))
    c = real_connect(daemon.DB_PATH)
    idx = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    c.close()
    check({"players_steamid", "hwids_token", "hwids_steamid"} <= idx, "hot lookups have indexes: %s" % sorted(i for i in idx if not i.startswith("sqlite_")))
    c = real_connect(daemon.DB_PATH)
    plan = " ".join(str(r) for r in c.execute("EXPLAIN QUERY PLAN SELECT token FROM players WHERE steamid=?", (76561198000000000,)))
    plan2 = " ".join(str(r) for r in c.execute("EXPLAIN QUERY PLAN SELECT hash FROM hwids WHERE token=?", ("x",)))
    c.close()
    check("players_steamid" in plan and "hwids_token" in plan2, "queries by steamid / hwid token use the indexes")
    # the file replaced under the daemon (restore from backup, deleted by hand): the schema is rebuilt, not assumed
    os.remove(daemon.DB_PATH)
    daemon.set_name(tok(1), "Alice")
    c = real_connect(daemon.DB_PATH)
    check(c.execute("SELECT name FROM players WHERE token=?", (tok(1),)).fetchone() == ("Alice",), "a deleted / replaced db file gets its schema again")
    c.close()

    # ---------------------------------------------------------------- dbc closes and rolls back
    with daemon._dblock, daemon.dbc() as c:
        c.execute("INSERT INTO players(token,name) VALUES(?,?)", (tok(2), "Bob"))
    try:
        c.execute("SELECT 1")
        closed = False
    except sqlite3.ProgrammingError:
        closed = True
    check(closed, "dbc() closes the connection when the block ends")
    try:
        with daemon._dblock, daemon.dbc() as c:
            c.execute("INSERT INTO players(token,name) VALUES(?,?)", (tok(3), "Carol"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    c = real_connect(daemon.DB_PATH)
    check(c.execute("SELECT 1 FROM players WHERE token=?", (tok(3),)).fetchone() is None and c.execute("SELECT 1 FROM players WHERE token=?", (tok(2),)).fetchone(),
          "an exception rolls the transaction back, a clean block commits")
    c.close()
    check(all(cc not in [] for cc in conns), "(bookkeeping)")

    # ---------------------------------------------------------------- name cache
    daemon._name_cache.clear(); daemon._steam_cache.clear()
    daemon.set_steam(tok(10), 76561198000000010, "Dora")
    n0 = len(conns)
    names = {daemon.get_name(tok(10)) for _ in range(200)}
    used = len(conns) - n0
    check(names == {"Dora"} and used <= 3, "200 get_name calls = %d DB connections (was 3 each)" % used)
    daemon.set_name(tok(10), "Dora2")
    check(daemon.get_name(tok(10)) == "Dora2", "set_name is visible at once (the writers invalidate the cache)")
    daemon.set_steam(tok(10), 76561198000000011, "Dora3")
    check(daemon.get_name(tok(10)) == "Dora3" and daemon.token_steamid(tok(10)) == 76561198000000011, "set_steam too (name + steam id)")
    with daemon._dblock, daemon.dbc() as c:
        c.execute("UPDATE players SET name='Hidden' WHERE token=?", (tok(10),))
    check(daemon.get_name(tok(10)) == "Dora3", "a direct SQL write is not seen until the cache entry expires (T2R_NAME_CACHE_S)")
    daemon.name_dirty()
    check(daemon.get_name(tok(10)) == "Hidden", "name_dirty() drops every entry")
    # custom name set through the in-game rename op
    import names as names_mod
    daemon.names_op(0xD2, tok(10).encode() + bytes([4]) + b"Zed1" + bytes([3]) + b"TAG")
    check(daemon.get_name(tok(10)) == "[TAG] Zed1", "the in-game rename shows up in get_name at once: %s" % daemon.get_name(tok(10)))
    check(daemon.get_name(None) is None and daemon.token_steamid("") == 0, "None / empty token")

    # ---------------------------------------------------------------- searching frame cache
    daemon._SF_CACHE.update(t=0.0, key=None, ents=[])
    for i in range(6):
        daemon.PRES.touch(tok(20 + i), "P%d" % i)
        daemon.set_name(tok(20 + i), "Searcher%d" % i)
        with daemon.MM.lock: daemon.MM.queue[tok(20 + i)] = time.time() + i
    daemon._name_cache.clear()
    n0 = len(conns)
    frames = [daemon.searching_frame(tok(20 + (k % 6))) for k in range(300)]
    used = len(conns) - n0
    check(used <= 40, "300 searching frames for 6 searchers = %d DB connections (was ~7500)" % used)
    f0 = daemon.searching_frame(tok(20))
    check(b"Searcher1" in f0 and b"Searcher0" not in f0 and f0[2] == 0x03, "a frame lists the others, not the recipient")
    check(len({daemon.searching_frame(tok(21)) for _ in range(5)}) == 1, "cached frames are identical")
    daemon.set_name(tok(22), "Renamed")
    check(b"Renamed" in daemon.searching_frame(tok(20)), "a rename invalidates the searching list cache")
    with daemon.MM.lock: daemon.MM.queue.clear()

    # ---------------------------------------------------------------- backup while writing
    daemon.sqlite3.connect = real_connect
    stop = threading.Event(); wrote = [0]; errs = []
    def writer():
        i = 0
        while not stop.is_set():
            try:
                daemon.save_loadout(tok(1000 + i % 400), os.urandom(300)); daemon.set_name(tok(1000 + i % 400), "W%d" % i)
                wrote[0] += 1
            except Exception as e:
                errs.append(repr(e))
            i += 1
    ths = [threading.Thread(target=writer, daemon=True) for _ in range(3)]
    for t in ths: t.start()
    okb = 0
    for _ in range(6):
        time.sleep(0.15)
        if daemon.db_backup():
            okb += 1
            check(daemon._db_ok(daemon.BAK_PATH), "backup #%d taken while 3 threads write is a valid database" % okb)
    stop.set()
    for t in ths: t.join(5)
    check(okb >= 4 and not errs and wrote[0] > 20,   # (only proves writes ran alongside; 100+ was a timing guess that failed under run_all -j 2)
           "backups succeed under concurrent writes (%d ok, %d writes, errors %s)" % (okb, wrote[0], errs[:2]))
    c = real_connect(daemon.BAK_PATH)
    nb = c.execute("SELECT COUNT(*) FROM players").fetchone()[0]; c.close()
    check(nb >= 1 and not os.path.exists(daemon.BAK_PATH + ".tmp"), "the backup has rows and no temp file is left (%d rows)" % nb)

    # ---------------------------------------------------------------- vacuum upkeep
    with daemon._dblock, daemon.dbc() as c:
        for i in range(600):
            c.execute("INSERT OR REPLACE INTO players(token,loadout) VALUES(?,?)", ("junk%d" % i, os.urandom(2000)))
    with daemon._dblock, daemon.dbc() as c:
        c.execute("DELETE FROM players WHERE token LIKE 'junk%'")
    sz0 = os.path.getsize(daemon.DB_PATH)
    r = daemon.db_maintenance()
    sz1 = os.path.getsize(daemon.DB_PATH)
    check(r.startswith("vacuumed") and sz1 < sz0 * 0.6, "db_maintenance vacuums when a quarter of the pages are free: %s, %d -> %d bytes" % (r, sz0, sz1))
    r = daemon.db_maintenance()
    check(r.startswith("ok"), "and leaves a compact db alone: %s" % r)
    check(daemon._db_ok(daemon.DB_PATH), "database intact after VACUUM")
    daemon._db_maint_last[0] = 0.0
    r1 = daemon.db_maintenance_tick(1000.0); r2 = daemon.db_maintenance_tick(1000.0 + 3599); r3 = daemon.db_maintenance_tick(1000.0 + 3601)
    r4 = daemon.db_maintenance_tick(1000.0 + 3700); r5 = daemon.db_maintenance_tick(1000.0 + 3601 + daemon.DB_MAINT_S + 1)
    check(r1 is None and r2 is None and r3 is not None and r4 is None and r5 is not None, "maintenance tick: armed on the first call, first pass an hour later, then once per DB_MAINT_S")

    # ---------------------------------------------------------------- new identities
    daemon.NEW_TOKENS.hits.clear()
    A = ("66.6.6.6", 5000)
    got = [daemon.new_identity_ok(tok(5000 + i), A) for i in range(daemon.NEW_TOKEN_N + 8)]
    check(got[:daemon.NEW_TOKEN_N] == [True] * daemon.NEW_TOKEN_N and not any(got[daemon.NEW_TOKEN_N:]), "a remote address may introduce %d new tokens per 10 min, then none" % daemon.NEW_TOKEN_N)
    check(daemon.new_identity_ok(tok(1), A), "a token the DB already knows is always fine (%s)" % tok(1)[:8])
    check(daemon.new_identity_ok(tok(7777), ("127.0.0.1", 1)) and daemon.new_identity_ok(tok(7778), None), "127.0.0.1 (host's own game / tools) is exempt")
    check(not daemon.new_identity_ok("zz" * 32, ("9.9.9.9", 1)), "a malformed token never creates anything")
    daemon.NEW_TOKENS.hits.clear()
    for i in range(daemon.NEW_TOKEN_N): daemon.NEW_TOKENS.allow("55.5.5.5")
    pl = tok(8888).encode() + bytes([4]) + b"Evil" + bytes([0])
    check(daemon._creates_rows(0xD2, pl, ("55.5.5.5", 1)) and daemon._creates_rows(0xE4, tok(8888).encode() + b"\x01", ("55.5.5.5", 1))
          and daemon._creates_rows(0xEE, tok(8888).encode() + b"\x01", ("55.5.5.5", 1)), "row-creating ops (name / side / booster) of a new identity over the limit are refused")
    check(not daemon._creates_rows(0xD0, tok(8888).encode(), ("55.5.5.5", 1)) and not daemon._creates_rows(0xE0, tok(8888).encode(), ("55.5.5.5", 1)),
          "read ops are never refused")

    class FakeConn:
        def __init__(self): self.out = b""
        def sendall(self, d): self.out += d
        def settimeout(self, t): pass
    def profile_batch(token):
        login = bytes([0x1c]) + token.encode() + b"\x01\x02\x07"
        login = login + bytes(346 - len(login))
        return [(0x0f, login)]
    daemon.NEW_TOKENS.hits.clear()
    rows0 = real_connect(daemon.DB_PATH).execute("SELECT COUNT(*) FROM players").fetchone()[0]
    for i in range(daemon.NEW_TOKEN_N + 10):
        st = {"token": None, "name": "PLAYER", "authed": False, "session": False, "is_bridge": False}
        daemon.handle_batch(FakeConn(), ("44.4.4.4", 2000 + i), st, profile_batch(tok(9000 + i)))
    c = real_connect(daemon.DB_PATH)
    rows1 = c.execute("SELECT COUNT(*) FROM players").fetchone()[0]; c.close()
    check(rows1 - rows0 == daemon.NEW_TOKEN_N, "a profile flood of random tokens from one address stores %d rows, not %d" % (rows1 - rows0, daemon.NEW_TOKEN_N + 10))
    st = {"token": None, "name": "PLAYER", "authed": False, "session": False, "is_bridge": False}
    daemon.handle_batch(FakeConn(), ("44.4.4.4", 1), st, profile_batch(tok(9000)))
    check(st["token"] == tok(9000), "a known token still logs in from that address")
finally:
    daemon.sqlite3.connect = real_connect

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
