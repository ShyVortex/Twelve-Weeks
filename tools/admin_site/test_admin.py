"""Tests for the admin site: python tools/admin_site/test_admin.py (stdlib unittest; temp files, loopback sockets on ephemeral ports)."""
import io
import json
import os
import sqlite3
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "update_server"))
import admin  # noqa: E402
import logindex  # noqa: E402
import report_store  # noqa: E402
import store  # noqa: E402


def tok(name, tail="ab"):
    return (b"T2N:" + name.encode() + b"\0").hex().ljust(40, "0") + (tail * 12)[:24]


ALICE, BOB, CAROL = tok("Alice", "a1"), tok("Bob", "b2"), tok("Carol", "c3")


def make_db(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE players(token TEXT PRIMARY KEY, name TEXT, loadout BLOB, kills INT DEFAULT 0, deaths INT DEFAULT 0, wins INT DEFAULT 0, matches INT DEFAULT 0, "
              "steamid INTEGER DEFAULT 0, last_seen REAL, parts_total INTEGER DEFAULT 0, parts_n INTEGER DEFAULT 0, draws INTEGER DEFAULT 0)")
    now = time.time()
    c.execute("INSERT INTO players(token,name,wins,matches,steamid,last_seen,parts_total,parts_n) VALUES(?,?,?,?,?,?,?,?)", (ALICE, "Alice", 3, 5, 7656119800000001, now - 60, 4000, 2))
    c.execute("INSERT INTO players(token,name,wins,matches,steamid,last_seen,draws) VALUES(?,?,?,?,?,?,?)", (BOB, "Bob", 1, 4, 7656119800000002, now - 86400, 1))
    c.execute("INSERT INTO players(token,name,matches,steamid,last_seen) VALUES(?,?,?,?,?)", (CAROL, "Carol", 0, 0, now - 5000))
    # a second install of Alice: same steam account = one player
    c.execute("INSERT INTO players(token,name,wins,matches,steamid,last_seen) VALUES(?,?,?,?,?,?)", (tok("Alice", "a9"), "Alice", 1, 1, 7656119800000001, now - 30))
    # reinstall without a Steam id under the same name (different case / spacing): folds into Alice's Steam account
    c.execute("INSERT INTO players(token,name,wins,matches,steamid,last_seen) VALUES(?,?,?,?,?,?)", (tok("alice", "e5"), " alice ", 1, 2, 0, now - 10))
    # Dave: two Steam-less installs = one person; a nameless install that never played is not listed
    c.execute("INSERT INTO players(token,name,wins,matches,steamid,last_seen) VALUES(?,?,?,?,?,?)", (tok("Dave", "d1"), "Dave", 1, 2, 0, now - 100))
    c.execute("INSERT INTO players(token,name,wins,matches,steamid,last_seen) VALUES(?,?,?,?,?,?)", (tok("Dave", "d2"), "dave", 0, 1, 0, now - 50))
    c.execute("INSERT INTO players(token,name,matches,steamid,last_seen) VALUES(?,?,?,?,?)", ("00" * 32, None, 0, 0, now - 9))
    c.execute("CREATE TABLE clans(token_id TEXT PRIMARY KEY, faction INT DEFAULT 0, status INT DEFAULT 0, day INT DEFAULT 0, healthy INT DEFAULT 0, hungry INT DEFAULT 0, sick INT DEFAULT 0, "
              "last_mid TEXT DEFAULT '', last_result TEXT DEFAULT '', weeks_total INT DEFAULT 0, runs_won INT DEFAULT 0, runs_lost INT DEFAULT 0, created REAL, updated REAL, "
              "boost_hi INT DEFAULT 1, meta TEXT DEFAULT '')")
    c.execute("INSERT INTO clans(token_id,faction,status,day,healthy,hungry,sick,last_result,weeks_total,updated) VALUES('s:7656119800000001',1,1,9,5,1,0,?,2,?)",
              (json.dumps({"parts": 900, "supplies": 18, "died": 0}), now))
    c.execute("INSERT INTO clans(token_id,faction,status,day,healthy,hungry,sick,last_result,updated) VALUES('s:7656119800000002',2,1,3,1,2,2,?,?)", (json.dumps({"died": 2}), now))
    c.execute("CREATE TABLE names(token_id TEXT PRIMARY KEY, name TEXT, tag TEXT, updated REAL)")
    c.execute("INSERT INTO names VALUES('s:7656119800000002','Bobby','XY',0)")
    c.commit()
    c.close()


def log_text(now):
    t = time.localtime(now - 3600)
    hdr = time.strftime("%a %b %d %H:%M:%S %Y", t)
    lt = lambda dt: time.strftime("%H:%M:%S", time.localtime(now - dt))  # noqa: E731
    return "\n".join([
        "# daemon " + hdr,
        "[%s] daemon version 5f499ac9 | require client version: True" % lt(3599),
        "[%s] TCP LISTEN 127.0.0.1:7001" % lt(3598),
        "[%s] EVT match-formed m1 players ['Alice', 'Bob'] host Alice net steam-p2p ping-ms {'Alice<>Bob': 33} client-versions {'Alice': '5f499ac9'}" % lt(3000),
        "[%s] EVT game-start m1 map to1-train-station players ['Alice', 'Bob']" % lt(2950),
        "[%s] EVT match-end m1 winner team 0 reported by Alice after 947 s players ['Alice', 'Bob']" % lt(2000),
        "[%s] EVT freed m1 ['Alice', 'Bob']" % lt(1990),
        "[%s] EVT match-formed m2 players ['Alice', 'Bob', 'Carol'] host Alice net server-relay ping-ms unknown client-versions {}" % lt(900),
        "[%s] EVT game-start m2 map to1-overpass players ['Alice', 'Bob', 'Carol']" % lt(850),
        "[%s] EVT left m2 Carol timed out | others stay: ['Alice', 'Bob', 'Carol']" % lt(500),
        "[%s] EVT match-formed m3 players ['Alice', 'Bob'] host Alice net steam-p2p ping-ms {} client-versions {}" % lt(700),
        "[%s] TCP ('1.2.3.4', 5) recv 71B 8f 01 0f 1c 35 34 33 32 34 65 33 61 34 34 36 35 35 33 37 39 36 65 36 33 36 33 30 30 30 30 30 30 30 30 30 30 ...(+30B)" % lt(400),
        "[%s] SESSION token 5432%s ERR something" % (lt(300), "ab" * 30),
        "[%s] HANDLER ERR (conn kept) KeyError('x')" % lt(200),
        "[%s] ANNOUNCE ('1.2.3.4', 5) Dave" % lt(10),
        "[%s] STATUS online=3 queue=1 matches=1 polls=4 tcp=5" % lt(5),
        ""])


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db = os.path.join(cls.tmp, "t2r.db")
        make_db(cls.db)
        now = time.time()
        cls.logp = os.path.join(cls.tmp, "daemon.log")
        with open(cls.logp, "w", encoding="utf-8") as f:
            f.write(log_text(now))
        with open(os.path.join(cls.tmp, "client_versions.json"), "w") as f:
            json.dump({ALICE: "5f499ac9", BOB: "old1"}, f)
        with open(os.path.join(cls.tmp, "linux_clients.json"), "w") as f:
            json.dump([BOB], f)
        cls.reports = os.path.join(cls.tmp, "reports")
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("meta.json", json.dumps({"text": "froze at loading", "name": "Alice", "version": "5f499ac9", "clips": 1}))
            z.writestr("files/play.log", "line one\nline two\n")
            z.writestr("files/screenshot-1.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
            z.writestr("files/crash.dmp", b"\0" * 10)
        cls.rep = report_store.save_report(cls.reports, b.getvalue(), "127.0.0.1")
        cls.clip = b"\0\0\0\x18ftypisom\0\0\0\0" + bytes(range(256)) * 4
        report_store.save_clip(cls.reports, cls.rep["code"], cls.rep["clipKey"], len(cls.clip), io.BytesIO(cls.clip))

    def mk(self, **kw):
        a = dict(db=self.db, daemon_log=self.logp, reports=self.reports, daemon="127.0.0.1:1")
        a.update(kw)
        return store.Admin(**a)


class TestLogIndex(Fixture):
    def test_matches_and_results(self):
        a = self.mk()
        ms = {m["id"]: m for m in a.derived_matches(a.logsnap())}
        self.assertEqual(ms["m1"]["state"], "ended")
        self.assertEqual(ms["m1"]["winner"], 0)
        self.assertEqual(logindex.result_for(ms["m1"], "Alice"), "W")
        self.assertEqual(logindex.result_for(ms["m1"], "Bob"), "L")
        self.assertEqual(ms["m1"]["map"], "to1-train-station")
        self.assertEqual(ms["m1"]["ping_ms"], 33)

    def test_idle_status_closes_open_matches(self):
        # newest STATUS says matches=1: m2 stays open, m3 (never started, >5 min) is closed
        a = self.mk()
        ms = {m["id"]: m for m in a.derived_matches(a.logsnap())}
        self.assertEqual(ms["m2"]["state"], "running")
        self.assertEqual(ms["m3"]["state"], "closed")

    def test_midnight_roll_and_restart(self):
        ev = logindex.LogIndex("")
        ev.cur_date = (2026, 10, 17)
        ev.last_secs = 23 * 3600 + 59 * 60
        ev._feed(["[00:00:05] EVT x y"], time.time())
        self.assertEqual(time.localtime(ev.events[0]["ts"]).tm_mday, 18)
        evs = [{"ts": 1, "kind": "match-formed", "body": "z players ['A']"}, {"ts": 2, "kind": "_start", "body": ""}]
        self.assertEqual(logindex.derive_matches(evs)[0]["closed_why"], "server restart")

    def test_incremental_read_and_rotation(self):
        p = os.path.join(self.tmp, "inc.log")
        open(p, "w").write("# daemon %s\n[01:00:00] EVT queue Alice queued: 1 waiting\n" % time.strftime("%a %b %d %H:%M:%S %Y"))
        li = logindex.LogIndex(p)
        li.refresh(0)
        self.assertEqual(len([e for e in li.events if e["kind"] == "queue"]), 1)
        open(p, "a").write("[01:00:05] EVT queue Bob queued: 2 waiting\n")
        li.refresh(0)
        self.assertEqual(len([e for e in li.events if e["kind"] == "queue"]), 2)
        open(p, "w").write("# daemon %s\n" % time.strftime("%a %b %d %H:%M:%S %Y"))     # truncated = rotated
        li.refresh(0)
        self.assertEqual(len([e for e in li.events if e["kind"] == "queue"]), 0)


class TestStore(Fixture):
    def test_overview_log_mode(self):
        o = self.mk().overview()
        self.assertEqual(o["source"], "log")
        self.assertEqual(o["server"]["version"], "5f499ac9")
        self.assertEqual(o["online"]["total"], 3)
        self.assertEqual(o["matchesRunning"], 1)
        self.assertTrue(o["notes"])
        self.assertEqual(o["totals"]["players"], 4)            # duplicate tokens fold into one person; the nameless never-played install is dropped
        self.assertEqual(o["totals"]["reportsNew"], 1)
        self.assertTrue(any("KeyError" in e["line"] for e in o["errors"]))
        self.assertFalse(o["canKick"])

    def test_snapshot_and_live_sources(self):
        snap = os.path.join(self.tmp, "t2r-status.json")
        live = {"started": time.time() - 100, "players": [{"name": "Alice", "pid": "aaaabbbbcccc", "steamid": 7656119800000001, "state": "match", "match": "m9", "idle_s": 1, "queued_s": None,
                                                           "version": "5f499ac9", "platform": "windows", "steam_helper": True}],
                "queue": [], "matches": [{"id": "m9", "state": "running", "age_s": 50, "map": {"level": "to1-overpass", "name": "Overpass"}, "mode": "", "net": "steam-p2p",
                                           "players": [{"name": "Alice", "pid": "aaaabbbbcccc", "team": 0, "left": False, "host": True, "ping_ms": None}],
                                           "clock": {"left": 300, "duration": 947, "ended": False, "age_s": 2}, "lives": {"team0": 12, "team1": 7, "age_s": 1}}]}
        json.dump({"ts": time.time(), "server_version": "5f499ac9", "live": live}, open(snap, "w"))
        try:
            a = self.mk()
            o = a.overview()
            self.assertEqual(o["source"], "snapshot")
            self.assertEqual(o["online"]["total"], 1)
            self.assertEqual(o["matchesRunning"], 1)
            on = a.players_online()
            self.assertEqual(on["players"][0]["clan"]["factionName"], "WLF")
            self.assertEqual(on["players"][0]["version"], "5f499ac9")
            self.assertFalse(on["canKick"])                     # snapshot only: no admin listener
            m = a.matches()
            self.assertEqual(m["live"][0]["lives"]["team0"], 12)
            self.assertNotIn(ALICE, json.dumps(on))
        finally:
            os.remove(snap)
        # a stale snapshot (older than 35 s) is not used
        json.dump({"ts": time.time() - 90, "live": live}, open(snap, "w"))
        try:
            self.assertEqual(self.mk().overview()["source"], "log")
        finally:
            os.remove(snap)

    def test_players_all_and_detail(self):
        a = self.mk()
        r = a.players_all("")
        self.assertEqual(r["total"], 4)
        names = {p["name"]: p for p in r["players"]}
        self.assertEqual(names["Alice"]["matches"], 8)         # 5 + 1 (second install, same Steam id) + 2 (Steam-less install, same name)
        self.assertEqual(names["Alice"]["wins"], 5)
        self.assertEqual({k.lower(): v for k, v in names.items()}["dave"]["matches"], 3)         # two Steam-less tokens merged by name
        self.assertEqual(len([p for p in r["players"] if p["name"].lower().strip() == "alice"]), 1)
        self.assertIn("[XY] Bobby", names)                     # custom name + tag
        self.assertEqual(names["[XY] Bobby"]["losses"], 2)     # 4 - 1 win - 1 draw
        self.assertEqual(a.players_all("bobby")["shown"], 1)
        self.assertEqual(a.players_all("7656119800000001")["shown"], 1)
        d = a.player(names["Alice"]["id"])
        self.assertTrue(d["ok"])
        self.assertEqual(d["installs"], 3)
        self.assertEqual(d["clan"]["factionName"], "WLF")
        self.assertEqual(d["clan"]["week"], 2)
        self.assertEqual(d["version"], "5f499ac9")
        self.assertTrue(any(h["result"] == "W" for h in d["history"]))
        self.assertEqual(d["reports"][0]["code"], self.rep["code"])
        bob = a.player(names["[XY] Bobby"]["id"])
        self.assertEqual(bob["platform"], "linux")
        self.assertTrue(bob["clan"]["risk"])                   # hungry+sick >= 60%, 2 died
        self.assertFalse(a.player("nope")["ok"])
        for blob in (json.dumps(r), json.dumps(d), json.dumps(a.clans())):
            for t in (ALICE, BOB, CAROL):
                self.assertNotIn(t, blob)
                self.assertNotIn(t[40:], blob)

    def test_online_one_row_per_person(self):
        snap = os.path.join(self.tmp, "t2r-status.json")
        pl = lambda pid, st, idle: {"name": "Alice", "pid": pid, "steamid": 7656119800000001 if pid != "bbbbbbbbbbbb" else 0, "state": st, "match": None, "idle_s": idle, "queued_s": None,   # noqa: E731
                                    "version": "5f499ac9", "platform": "windows", "steam_helper": True}
        live = {"started": time.time(), "players": [pl("aaaaaaaaaaaa", "menu", 1), pl("bbbbbbbbbbbb", "match", 2)], "queue": [], "matches": []}
        with open(snap, "w") as f:
            json.dump({"ts": time.time(), "server_version": "5f499ac9", "live": live}, f)
        try:
            on = self.mk().players_online()["players"]
            self.assertEqual(len(on), 1)
            self.assertEqual(on[0]["state"], "match")          # the most active connection wins
        finally:
            os.remove(snap)

    def test_clans(self):
        c = self.mk().clans()
        self.assertEqual(c["alive"], 2)
        self.assertEqual(c["atRisk"], 1)
        self.assertFalse(c["feedAvailable"])                   # no clan_feed table in the fixture

    def test_matches_history(self):
        h = self.mk().matches()["history"]
        self.assertTrue(any(m["result"] == "TEAM 1 WON" and m["map"] == "Train Station" for m in h))
        self.assertFalse(any(m["id"] == "m3" for m in h))      # never started: not history
        m2 = [m for m in self.mk().matches()["live"] if m["id"] == "m2"][0]
        self.assertEqual(len(m2["players"]), 3)

    def test_db_is_not_modified(self):
        before = os.path.getmtime(self.db), os.path.getsize(self.db)
        a = self.mk()
        a.overview(); a.players_all(""); a.clans(); a.matches()
        self.assertEqual(before, (os.path.getmtime(self.db), os.path.getsize(self.db)))
        # a locked database (writer holding the lock) must not hang or crash a read
        w = sqlite3.connect(self.db, timeout=0)
        w.execute("BEGIN EXCLUSIVE")
        try:
            t0 = time.time()
            a2 = self.mk()
            try:
                a2.players_all("")
            except Exception:    # noqa: BLE001
                pass
            self.assertLess(time.time() - t0, 5)
        finally:
            w.rollback(); w.close()

    def test_logs_redact_filter(self):
        a = self.mk()
        r = a.logs(quiet=False, n=1000)
        blob = json.dumps(r)
        self.assertNotIn("5432" + "ab" * 30, blob)
        self.assertNotIn("35 34 33 32 34 65", blob)
        self.assertIn("<id>", blob)
        self.assertTrue(any(l["c"] == "err" for l in r["lines"]))
        self.assertEqual(len(a.logs(level="err", quiet=False)["lines"]), 2)
        self.assertEqual(len(a.logs(q="timed out")["lines"]), 1)
        self.assertFalse(any("recv" in l["t"] for l in a.logs(quiet=True)["lines"]))
        self.assertFalse(a.logs(which="../x")["ok"])
        self.assertEqual(store.redact("tok " + "ab" * 32), "tok <id>")

    def test_reports(self):
        a = self.mk()
        lst = a.reports_list()
        self.assertEqual(lst["new"], 1)
        code = self.rep["code"]
        r = a.report(code)
        self.assertTrue(r["ok"])
        self.assertEqual({f["name"]: f["text"] for f in r["files"]}, {"play.log": True, "crash.dmp": False, "screenshot-1.png": False, "clip-1.mp4": False})
        self.assertEqual([f["name"] for f in r["files"] if f["image"]], ["screenshot-1.png"])
        ct, data = a.report_image(code, "screenshot-1.png")
        self.assertEqual(ct, "image/png"); self.assertTrue(data.startswith(b"\x89PNG"))
        for bad in ("crash.dmp", "play.log", "../meta.json", "..\meta.json", "files/screenshot-1.png", "screenshot-9.png"):
            self.assertIsNone(a.report_image(code, bad), bad)
        self.assertIsNone(a.report_image("../..", "screenshot-1.png"))
        self.assertIn("line one", a.report_file(code, "play.log")["text"])
        self.assertIsNone(a.report_file(code, "../meta.json"))
        self.assertIsNone(a.report_file("R-ZZZZ", "play.log"))
        self.assertIsNone(a.find_report("../.."))
        self.assertTrue(a.mark_handled(code)["ok"])
        self.assertEqual(a.reports_list()["new"], 0)
        self.assertTrue(json.load(open(os.path.join(self.rep["dir"], "meta.json")))["handled"])
        a.mark_handled(code, False)
        self.assertEqual(a.reports_list()["new"], 1)
        self.assertFalse(a.mark_handled("R-NOPE")["ok"])

    def test_kick_needs_listener(self):
        a = self.mk(admin_url="http://127.0.0.1:1")
        self.assertFalse(a.kick("abcdef012345")["ok"])         # no secret file
        open(os.path.join(self.tmp, "admin-secret.txt"), "w").write("s" * 32)
        try:
            r = self.mk(admin_url="http://127.0.0.1:1").kick("abcdef012345")
            self.assertFalse(r["ok"])
            self.assertIn("restart", r["error"])
            self.assertFalse(a.kick("../x")["ok"])
        finally:
            os.remove(os.path.join(self.tmp, "admin-secret.txt"))


class FakeDaemon(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def _j(self, o, c=200):
        b = json.dumps(o).encode()
        self.send_response(c); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.headers.get("X-Admin-Secret") != "s" * 32:
            return self._j({"ok": False}, 403)
        self._j({"ok": True, "server_version": "v1", "live": {"started": time.time(), "players": [{"name": "Zed", "pid": "0123456789ab", "steamid": 0, "state": "menu", "match": None, "idle_s": 0,
                                                                                                 "queued_s": None, "version": "v1", "platform": "windows", "steam_helper": True}],
                                                              "queue": [], "matches": []}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        FakeDaemon.seen.append((self.path, self.headers.get("X-Admin-Secret"), json.loads(self.rfile.read(n))))
        self._j({"ok": True, "name": "Zed", "did": ["queue"]})


class TestHttp(Fixture):
    def setUp(self):
        self.fd = HTTPServer(("127.0.0.1", 0), FakeDaemon)
        threading.Thread(target=self.fd.serve_forever, daemon=True).start()
        open(os.path.join(self.tmp, "admin-secret.txt"), "w").write("s" * 32)
        a = self.mk(admin_url="http://127.0.0.1:%d" % self.fd.server_address[1], launcher_dir=admin.default_launcher_dir())
        self.srv = admin.make_server(a, 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown(); self.fd.shutdown()
        os.remove(os.path.join(self.tmp, "admin-secret.txt"))

    def req(self, path, method="GET", data=None, headers=None, host=None):
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=json.dumps(data).encode() if data is not None else None, method=method)
        r.add_header("Host", host or "127.0.0.1:%d" % self.port)
        for k, v in (headers or {}).items():
            r.add_header(k, v)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_clan_page(self):
        """The launcher's CLAN tab inside the admin: /clan.html + the launcher's own scripts / styles / assets + /api/clanview (read-only)."""
        names = {p["name"]: p for p in json.loads(self.req("/api/players")[1])["players"]}
        pid = names["Alice"]["id"]
        c, b, h = self.req("/clan.html?id=" + pid)
        self.assertEqual(c, 200)
        self.assertIn(b"/launcher/src/clan.js", b)
        self.assertIn("frame-ancestors 'self'", h["Content-Security-Policy"])
        self.assertEqual(self.req("/clanframe.js")[0], 200)
        c, b, h = self.req("/api/clanview?id=" + pid)
        d = json.loads(b)
        self.assertTrue(d["ok"])
        self.assertTrue(d["clan"]["hasClan"])
        self.assertEqual(d["clan"]["factionName"], "WLF")
        self.assertEqual((d["clan"]["week"], d["clan"]["dayOfWeek"]), (2, 3))
        self.assertTrue(d["feed"]["hasClan"])
        self.assertFalse(json.loads(self.req("/api/clanview?id=nobody")[1])["ok"])
        self.assertEqual(self.req("/api/clanview?id=" + pid, method="POST", data={})[0], 403)     # read-only: no write path
        if self.launcher_root:
            for p in ("/launcher/src/clan.js", "/launcher/src/neat.css", "/launcher/src/i18n/pl.json", "/launcher/assets/icons/skill-fortitude.png", "/assets/icons/skill-fortitude.png"):
                self.assertEqual(self.req(p)[0], 200, p)
            for p in ("/launcher/src/../main/clan.js", "/launcher/main/clan.js", "/launcher/src/app/core.js", "/launcher/assets/sounds/x.ogg", "/launcher/src/%2e%2e/preload.js"):
                self.assertEqual(self.req(p)[0], 404, p)

    @property
    def launcher_root(self):
        return os.path.isdir(admin.default_launcher_dir() or "")

    def test_binds_loopback_only(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_static_and_api(self):
        c, b, h = self.req("/")
        self.assertEqual(c, 200)
        self.assertIn(b"ADMIN", b)
        self.assertIn("script-src 'self'", h["Content-Security-Policy"])
        self.assertEqual(self.req("/admin.css")[0], 200)
        self.assertEqual(self.req("/admin.js")[0], 200)
        self.assertEqual(self.req("/static/../admin.py")[0], 404)
        self.assertEqual(self.req("/..%2fadmin.py")[0], 404)
        c, b, _ = self.req("/api/overview")
        j = json.loads(b)
        self.assertEqual(j["source"], "live")
        self.assertTrue(j["canKick"])
        self.assertEqual(json.loads(self.req("/api/online")[1])["players"][0]["name"], "Zed")
        for p in ("/api/players", "/api/matches", "/api/clans", "/api/reports", "/api/logs"):
            self.assertEqual(self.req(p)[0], 200, p)
        self.assertEqual(self.req("/api/report-file?code=R-ZZZZ&name=x")[0], 404)
        code = self.rep["code"]
        c, b, h = self.req("/api/report-image?code=%s&name=screenshot-1.png" % code)
        self.assertEqual((c, h["Content-Type"], h["X-Content-Type-Options"]), (200, "image/png", "nosniff"))
        self.assertTrue(b.startswith(b"\x89PNG"))
        self.assertEqual(self.req("/api/report-image?code=%s&name=crash.dmp" % code)[0], 404)
        v = "/api/report-video?code=%s&name=clip-1.mp4" % code
        c, b, h = self.req(v)
        self.assertEqual((c, h["Content-Type"], h["Accept-Ranges"]), (200, "video/mp4", "bytes"))
        self.assertEqual(b, self.clip)
        c, b, h = self.req(v, headers={"Range": "bytes=100-199"})
        self.assertEqual((c, h["Content-Range"], b), (206, "bytes 100-199/%d" % len(self.clip), self.clip[100:200]))
        c, b, h = self.req(v, headers={"Range": "bytes=-10"})
        self.assertEqual((c, b), (206, self.clip[-10:]))
        self.assertEqual(self.req(v, headers={"Range": "bytes=99999-"})[0], 416)
        for bad in ("crash.dmp", "screenshot-1.png", "..%2fmeta.json", "clip-2.mp4"):
            self.assertEqual(self.req("/api/report-video?code=%s&name=%s" % (code, bad))[0], 404, bad)
        self.assertNotIn(b"clipKey", self.req("/api/report?code=%s" % code)[1])
        self.assertEqual(self.req("/api/report-image?code=%s&name=..%%2fmeta.json" % code)[0], 404)

    def test_bad_host_rejected(self):
        self.assertEqual(self.req("/api/overview", host="evil.example:80")[0], 403)

    def test_post_needs_header_and_origin(self):
        self.assertEqual(self.req("/api/kick", "POST", {"pid": "0123456789ab"})[0], 403)
        self.assertEqual(self.req("/api/kick", "POST", {"pid": "0123456789ab"}, {"X-Admin-Request": "1", "Origin": "http://evil.example"})[0], 403)
        FakeDaemon.seen.clear()
        c, b, _ = self.req("/api/kick", "POST", {"pid": "0123456789ab"}, {"X-Admin-Request": "1", "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(c, 200)
        self.assertTrue(json.loads(b)["ok"])
        self.assertEqual(FakeDaemon.seen[0], ("/kick", "s" * 32, {"pid": "0123456789ab"}))
        self.assertFalse(json.loads(self.req("/api/kick", "POST", {"pid": "zz"}, {"X-Admin-Request": "1"})[1])["ok"])

    def test_kick_reason_forwarded(self):
        hdr = {"X-Admin-Request": "1", "Origin": "http://127.0.0.1:%d" % self.port}
        FakeDaemon.seen.clear()
        self.assertTrue(json.loads(self.req("/api/kick", "POST", {"pid": "0123456789ab", "reason": "  be \x00nice\n " + "x" * 200}, hdr)[1])["ok"])
        sent = FakeDaemon.seen[0][2]
        self.assertEqual(sent["pid"], "0123456789ab")
        self.assertTrue(sent["reason"].startswith("be nice xxx") and len(sent["reason"]) == 120)
        FakeDaemon.seen.clear()
        self.req("/api/kick", "POST", {"pid": "0123456789ab", "reason": "   "}, hdr)
        self.assertEqual(FakeDaemon.seen[0][2], {"pid": "0123456789ab"})        # empty reason = the old request body

    def test_handled_endpoint(self):
        code = self.rep["code"]
        c, b, _ = self.req("/api/report-handled", "POST", {"code": code, "handled": True}, {"X-Admin-Request": "1"})
        self.assertTrue(json.loads(b)["ok"])
        self.req("/api/report-handled", "POST", {"code": code, "handled": False}, {"X-Admin-Request": "1"})


class TestNews(Fixture):
    """Patch notes editor: news.json of the update server, validated, atomic, backed up."""
    @classmethod
    def setUpClass(cls):     # no report store needed here
        cls.tmp = tempfile.mkdtemp()
        cls.db = os.path.join(cls.tmp, "t2r.db")
        make_db(cls.db)
        cls.logp = os.path.join(cls.tmp, "daemon.log")
        open(cls.logp, "w").write("")
        cls.reports = os.path.join(cls.tmp, "reports")

    def setUp(self):
        self.data = tempfile.mkdtemp()
        self.np = os.path.join(self.data, "news.json")
        self.entry = {"id": 2, "date": "2026-11-06", "build": "170", "kind": "build", "stamp": "abc", "headline": "Two",
                      "sections": {"new": ["a", "b"]}, "pl": {"headline": "Dwa", "sections": {"new": ["aa", "bb"]}}}
        json.dump([self.entry, {"id": 1, "date": "2026-11-01", "headline": "One", "sections": {}}], open(self.np, "w", encoding="utf-8"))
        self.a = self.mk(update_data=self.data)
        self.srv = admin.make_server(self.a, 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()

    def post(self, entries, hdr=True):
        r = urllib.request.Request("http://127.0.0.1:%d/api/news" % self.port, data=json.dumps({"entries": entries}).encode(), method="POST")
        if hdr:
            r.add_header("X-Admin-Request", "1")
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_get_and_save(self):
        g = self.a.news_get()
        self.assertTrue(g["ok"])
        self.assertEqual([e["id"] for e in g["entries"]], [2, 1])
        e = dict(self.entry, headline="Two edited", sections={"new": ["b", " ", "a"]})
        e["pl"] = {"headline": "Dwa", "sections": {"new": ["bb", "aa"]}}
        new = {"id": 3, "date": "2026-11-07", "build": "171", "kind": "hotfix", "stamp": "", "headline": "Three", "sections": {"fixed": ["x"]}, "pl": {"headline": "", "sections": {}}}
        c, r = self.post([new, e])
        self.assertEqual((c, r["ok"], r["count"]), (200, True, 2))
        d = json.load(open(self.np, encoding="utf-8"))
        self.assertEqual([x["id"] for x in d], [3, 2])
        self.assertEqual(d[1]["sections"]["new"], ["b", "a"])         # blank line dropped, order kept
        self.assertEqual(d[1]["headline"], "Two edited")
        bd = os.path.join(self.data, "news-backups")
        self.assertEqual(len(os.listdir(bd)), 1)
        self.assertEqual(json.load(open(os.path.join(bd, os.listdir(bd)[0]), encoding="utf-8"))[0]["headline"], "Two")   # the old file
        self.assertFalse(os.path.exists(self.np + ".tmp"))

    def test_backups_pruned(self):
        for i in range(25):
            self.assertTrue(self.a.news_save([dict(self.entry, headline="v%d" % i)])["ok"])
        self.assertEqual(len(os.listdir(os.path.join(self.data, "news-backups"))), 20)

    def test_validation_keeps_file(self):
        before = open(self.np, "rb").read()
        for bad in ([{"id": 1, "headline": "x"}, {"id": 1, "headline": "y"}], [{"headline": "x"}], [{"id": 5, "headline": " "}],
                    [{"id": 5, "headline": "x", "sections": {"new": "not a list"}}], [{"id": 5, "headline": "x", "date": "yesterday"}], "nope"):
            c, r = self.post(bad)
            self.assertFalse(r["ok"], bad)
        self.assertEqual(open(self.np, "rb").read(), before)
        self.assertFalse(os.path.exists(os.path.join(self.data, "news-backups")))

    def test_post_needs_csrf_header_and_update_data(self):
        self.assertEqual(self.post([self.entry], hdr=False)[0], 403)
        self.assertFalse(self.mk().news_save([self.entry])["ok"])
        self.assertFalse(self.mk().news_get()["ok"])

    def test_editor_page_is_served(self):
        for path in ("/news.html", "/newsframe.js"):
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertIn(b"/launcher/src/app/news.js" if path.endswith("html") else b"newsItem", r.read())

    def test_big_body_and_update_server_reads_fresh(self):
        big = dict(self.entry, sections={"new": ["line %d " % i + "x" * 100 for i in range(300)]})     # > 8 KB body
        self.assertTrue(self.post([big])[1]["ok"])
        import importlib.util
        sp = importlib.util.spec_from_file_location("t2r_update_server", os.path.join(HERE, "..", "update_server", "server.py"))
        us = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(us)
        self.assertEqual(len(us.Store(self.data).read_json("news.json", [])[0]["sections"]["new"]), 300)    # the update server reads the file per call


if __name__ == "__main__":
    unittest.main(verbosity=1)
