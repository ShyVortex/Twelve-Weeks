#!/usr/bin/env python3
"""Twelve Weeks admin site: a LOCAL, launcher-styled web page for the server owner (stdlib only, binds 127.0.0.1).

  python tools/admin_site/admin.py --db <path to t2r.db> [--port 7010] [--daemon-log <daemon.log>] [--reports <dir>]
         [--daemon 127.0.0.1:7001] [--admin-url http://127.0.0.1:7011] [--update-data <update server data dir>]

Open http://127.0.0.1:7010/ . Read-only: the database is opened mode=ro; the only writes are the bug-report 'handled' flag (report store) and, when
you confirm it, a kick request to the daemon's loopback admin listener. See README.md.
"""
import argparse
import json
import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from store import Admin  # noqa: E402

STATIC = os.path.join(HERE, "static")
CSP = "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self'"


def default_launcher_dir():
    p = os.path.normpath(os.path.join(HERE, "..", "..", "release", "launcher", "assets"))
    return p if os.path.isdir(p) else ""


def make_handler(admin, port_ref):
    bgdir = os.path.join(admin.launcher_dir, "bg") if admin.launcher_dir else ""
    launcher_root = os.path.dirname(admin.launcher_dir) if admin.launcher_dir else ""     # release/launcher: the CLAN page reuses its scripts, styles and assets as they are

    class H(BaseHTTPRequestHandler):
        server_version = "t2r-admin/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def host_ok(self):
            h = (self.headers.get("Host") or "").lower()
            return h in ("127.0.0.1:%d" % port_ref[0], "localhost:%d" % port_ref[0], "[::1]:%d" % port_ref[0])

        def send_bytes(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def send_range(self, path, ctype, size):
            """A file with HTTP Range support (206), streamed in 1 MB pieces, so a <video> can seek without loading a whole clip."""
            start, end, code = 0, size - 1, 200
            rng = self.headers.get("Range", "")
            m = re.match(r"^bytes=(\d*)-(\d*)$", rng.strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start > end or start >= size:
                    return self.send_bytes(416, b"bad range", "text/plain", {"Content-Range": "bytes */%d" % size})
                code = 206
            n = end - start + 1
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(n))
            self.send_header("Accept-Ranges", "bytes")
            if code == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as fh:
                fh.seek(start)
                left = n
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def json(self, obj, code=200):
            self.send_bytes(code, json.dumps(obj, default=str).encode("utf-8"), "application/json; charset=utf-8")

        def static(self, rel):
            p = os.path.normpath(os.path.join(STATIC, rel))
            if not p.startswith(STATIC + os.sep) or not os.path.isfile(p):
                return self.send_bytes(404, b"not found", "text/plain")
            with open(p, "rb") as f:
                body = f.read()
            self.send_bytes(200, body, mimetypes.guess_type(p)[0] or "application/octet-stream")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self.host_ok():
                return self.send_bytes(403, b"bad host", "text/plain")
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            p = u.path
            try:
                if p in ("/", "/index.html"):
                    return self.static("index.html")
                if p in ("/admin.css", "/admin.js", "/clan.html", "/clanframe.js", "/news.html", "/newsframe.js"):
                    return self.static(p[1:])
                m = re.match(r"^/(?:launcher/)?(src/(?:(?:app/)?[a-z0-9-]+\.(?:js|css)|i18n/[a-z-]+\.json)|assets/(?:portraits|icons|bg)/[A-Za-z0-9_-]+\.(?:png|jpg))$", p)
                if m and launcher_root and os.path.isfile(os.path.join(launcher_root, m.group(1))):
                    with open(os.path.join(launcher_root, m.group(1)), "rb") as f:
                        return self.send_bytes(200, f.read(), mimetypes.guess_type(p)[0] or "application/octet-stream", {"Cache-Control": "max-age=300"})
                m = re.match(r"^/bg/([a-z0-9-]+\.jpg)$", p)
                if m and bgdir and os.path.isfile(os.path.join(bgdir, m.group(1))):
                    with open(os.path.join(bgdir, m.group(1)), "rb") as f:
                        return self.send_bytes(200, f.read(), "image/jpeg", {"Cache-Control": "max-age=3600"})
                if p == "/api/overview":
                    return self.json(admin.overview())
                if p == "/api/online":
                    return self.json(admin.players_online())
                if p == "/api/players":
                    return self.json(admin.players_all(q.get("q", "")))
                if p == "/api/player":
                    return self.json(admin.player(q.get("id", "")))
                if p == "/api/notices":
                    return self.json(admin.notices())
                if p == "/api/matches":
                    return self.json(admin.matches())
                if p == "/api/teams":
                    return self.json(admin.teams())
                if p == "/api/clanview":
                    return self.json(admin.clanview(q.get("id", ""), q.get("lang", "en")))
                if p == "/api/clans":
                    return self.json(admin.clans())
                if p == "/api/reports":
                    return self.json(admin.reports_list())
                if p == "/api/clan-backups":
                    return self.json(admin.clan_backups(q.get("id", "")))
                if p == "/api/report":
                    return self.json(admin.report(q.get("code", "")))
                if p == "/api/report-file":
                    r = admin.report_file(q.get("code", ""), q.get("name", ""))
                    return self.json(r) if r else self.json({"error": "no such file"}, 404)
                if p == "/api/report-image":
                    r = admin.report_image(q.get("code", ""), q.get("name", ""))
                    return self.send_bytes(200, r[1], r[0], {"Content-Disposition": "inline", "Cache-Control": "private, max-age=3600"}) if r else self.send_bytes(404, b"no such image", "text/plain")
                if p == "/api/report-video":
                    r = admin.report_video(q.get("code", ""), q.get("name", ""))
                    return self.send_range(r[0], r[1], r[2]) if r else self.send_bytes(404, b"no such video", "text/plain")
                if p == "/api/news":
                    return self.json(admin.news_get())
                if p == "/api/logs":
                    return self.json(admin.logs(q.get("q", ""), q.get("level", "all"), q.get("file", "0"), min(int(q.get("n", "300") or 300), 1000),
                                                q.get("quiet", "1") != "0"))
                return self.send_bytes(404, b"not found", "text/plain")
            except BrokenPipeError:
                raise
            except Exception as e:    # noqa: BLE001 - a bad request / read never takes the site down
                try:
                    self.json({"error": "%s: %s" % (type(e).__name__, e)}, 500)
                except OSError:
                    pass

        def do_POST(self):
            if not self.host_ok():
                return self.send_bytes(403, b"bad host", "text/plain")
            # CSRF: only the page's own script (custom header + same origin) may write
            origin = self.headers.get("Origin")
            if self.headers.get("X-Admin-Request") != "1" or (origin and urlparse(origin).netloc.lower() != (self.headers.get("Host") or "").lower()):
                return self.json({"ok": False, "error": "forbidden"}, 403)
            try:
                p = urlparse(self.path).path
                n = min(int(self.headers.get("Content-Length") or 0), 2 << 20 if p == "/api/news" else 8192)
                body = json.loads(self.rfile.read(n) or b"{}")
                if p == "/api/news":
                    return self.json(admin.news_save(body.get("entries")))
                if p == "/api/kick":
                    return self.json(admin.kick(str(body.get("pid", "")), str(body.get("reason") or "")))
                if p == "/api/clan-reset":
                    return self.json(admin.clan_reset(str(body.get("id", "")), str(body.get("confirm", "")), bool(body.get("names", False))))
                if p == "/api/clan-restore":
                    return self.json(admin.clan_restore(str(body.get("id", "")), str(body.get("file", ""))))
                if p == "/api/notice":
                    return self.json(admin.notice_send(str(body.get("text", "")), float(body.get("seconds", 8) or 8), str(body.get("text_pl", "") or "")))
                if p == "/api/notice-clear":
                    return self.json(admin.notice_clear(int(body.get("id", -1))))
                if p == "/api/shutdown":
                    return self.json(admin.shutdown_schedule(float(body.get("minutes", 5)), str(body.get("reason", "")), bool(body.get("restart", True)), str(body.get("reason_pl", "") or "")))
                if p == "/api/shutdown-cancel":
                    return self.json(admin.shutdown_cancel())
                if p == "/api/teams":
                    return self.json(admin.teams_set(str(body.get("rules", ""))))
                if p == "/api/teams-move":
                    return self.json(admin.teams_move(str(body.get("pid", ""))))
                if p == "/api/report-handled":
                    return self.json(admin.mark_handled(str(body.get("code", "")), bool(body.get("handled", True))))
                return self.json({"ok": False, "error": "unknown action"}, 404)
            except (ValueError, TypeError):
                return self.json({"ok": False, "error": "bad request"}, 400)
            except Exception as e:    # noqa: BLE001
                return self.json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)

    return H


def make_server(admin, port=7010):
    ref = [port]
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(admin, ref))
    ref[0] = srv.server_address[1]
    srv.daemon_threads = True
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="the daemon's t2r.db (opened read-only)")
    ap.add_argument("--port", type=int, default=7010)
    ap.add_argument("--daemon-log", default="", help="daemon.log (rotated .1 .2 ... are read too); 'auto' = the newest dist/*/host/daemon.log, followed when the server moves to a new PT folder")
    ap.add_argument("--reports", default="", help="bug report store folder (update server <data>/reports)")
    ap.add_argument("--daemon", default="", help="host:port of the game port to probe (default: from the log, else 127.0.0.1:7001)")
    ap.add_argument("--admin-url", default="http://127.0.0.1:7011", help="the daemon's loopback admin listener (T2R_ADMIN_PORT)")
    ap.add_argument("--status-file", default="", help="daemon snapshot (default <db dir>/t2r-status.json)")
    ap.add_argument("--update-data", default="", help="update server data dir (channels.json: latest published build)")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.db):
        sys.exit("database not found: " + a.db)
    admin = Admin(a.db, a.daemon_log, a.reports, a.daemon, a.status_file, a.admin_url, "", a.update_data, default_launcher_dir())
    srv = make_server(admin, a.port)
    print("Twelve Weeks admin site: http://127.0.0.1:%d/   (db %s, read-only)" % (srv.server_address[1], a.db), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
