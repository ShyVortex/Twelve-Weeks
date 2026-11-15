#!/usr/bin/env python3
"""Twelve Weeks admin site: a web page for the server owner, styled like twelve-weeks.com (stdlib only, binds 127.0.0.1 by default; --bind 0.0.0.0 + a users file for LAN access).

  python tools/admin_site/admin.py --db <path to t2r.db> [--port 7010] [--daemon-log <daemon.log>] [--reports <dir>]
         [--daemon 127.0.0.1:7001] [--admin-url http://127.0.0.1:7011] [--update-data <update server data dir>]

         [--tunnel-host admin.twelve-weeks.com] [--site-url https://twelve-weeks.com] [--web-secret F] [--web-admins F] [--users F]

Open http://127.0.0.1:7010/ . Read-only: the database is opened mode=ro; the only writes are the bug-report 'handled' flag (report store) and, when
you confirm it, a kick request to the daemon's loopback admin listener. See README.md.
"""
import argparse
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import time
import mimetypes
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from store import Admin  # noqa: E402

STATIC = os.path.join(HERE, "static")
CSP = ("default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; frame-ancestors 'self'")
PUBLIC_PATHS = ("/admin.css",)      # served before login (the styled login / not-admin pages need it)
SESSION_COOKIE = "tw_s"             # the website's session cookie: "<steamid>.<exp>.<hmac-sha256(web-secret, 'sid.exp')>" (tools/web/web.py)


def default_launcher_dir():
    p = os.path.normpath(os.path.join(HERE, "..", "..", "release", "launcher", "assets"))
    return p if os.path.isdir(p) else ""


def load_users(path):
    """{name: token} from a file with one 'name token' per line (# comments). Missing file = no remote users. Revoke = delete the line (re-read on every request)."""
    users = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    parts = ln.split(None, 1)
                    if len(parts) == 2:
                        users[parts[0]] = parts[1].strip()
    except OSError:
        pass
    return users


_FILE_CACHE = {}


def _read_cached(path, parse):
    """parse(file text) cached by mtime; a missing / unreadable file = parse('') (re-read as soon as it changes)."""
    try:
        mt = os.stat(path).st_mtime_ns
    except OSError:
        return parse("")
    hit = _FILE_CACHE.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            val = parse(f.read())
    except OSError:
        val = parse("")
    _FILE_CACHE[path] = (mt, val)
    return val


def load_web_admins(path):
    """Steam64 ids (one per line, # comments) of the website admins; the same file web.py uses for news editing."""
    def parse(txt):
        ids = set()
        for ln in txt.splitlines():
            e = ln.split("#", 1)[0].strip()
            if e.isdigit():
                ids.add(int(e))
        return ids
    return _read_cached(path, parse) if path else set()


def load_web_secret(path):
    return _read_cached(path, lambda t: t.strip().encode()) if path else b""


def cookie_sid(cookie_header, secret):
    """Steam id of a valid, unexpired website session cookie (same format and HMAC as web.py's session_info), else None."""
    if not secret:
        return None
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == SESSION_COOKIE:
            try:
                sid, exp, mac = v.split(".")
                want = hmac.new(secret, ("%s.%d" % (sid, int(exp))).encode(), hashlib.sha256).hexdigest()
                if sid.isdigit() and int(exp) > time.time() and hmac.compare_digest(mac, want):
                    return int(sid)
            except (ValueError, TypeError):
                return None
    return None


STEAM_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 0 0-9.96 9.2l5.35 2.21a2.8 2.8 0 0 1 1.6-.5h.16l2.38-3.45v-.05a3.77 3.77 0 1 1 3.77 3.77h-.09l-3.4 2.42v.13a2.83 2.83 0 0 1-5.6.57L2.4 15.1A10 10 0 1 0 12 2zM8.28 17.17l-1.22-.5a2.12 2.12 0 1 0 1.16-2.9l1.27.52a1.56 1.56 0 1 1-1.2 2.88zm9.51-7.74a2.51 2.51 0 1 0-2.51 2.51 2.51 2.51 0 0 0 2.51-2.51zm-4.4 0a1.89 1.89 0 1 1 1.89 1.89 1.89 1.89 0 0 1-1.89-1.89z"/></svg>')


def gate_page(kind, site_url, admin_origin, sid=0):
    """Styled HTML for the two gate pages: kind 'login' (Steam button + small token link) or 'notadmin' (shows the Steam id to send to the owner)."""
    try:
        with open(os.path.join(STATIC, "login.html"), encoding="utf-8") as f:
            tpl = f.read()
    except OSError:
        tpl = "<!doctype html><title>Admin</title><!--BODY-->"
    site = html.escape(site_url.rstrip("/"), quote=True)
    if kind == "notadmin":
        body = ('<h1>Not an admin</h1><p class="lead">You are logged in with Steam, but this account is not on the admin list of this server.</p>'
                '<div class="idbox"><span>Your Steam ID</span><b>%d</b></div>'
                '<p class="hint">Send this number to the server owner. They add it to <code>data/web-admins.txt</code>, then reload this page.</p>'
                '<div class="gate-actions"><a class="btn" href="%s/auth/logout">Log out</a></div>' % (sid, site))
    else:
        nxt = quote(admin_origin.rstrip("/") + "/", safe="")
        body = ('<h1>Admin login</h1><p class="lead">Log in with the Steam account of a server admin.</p>'
                '<div class="gate-actions"><a class="btn main" href="%s/auth/steam?next=%s">%sLog in with Steam</a></div>'
                '<p class="hint"><a href="/login-token">Use an access token</a></p>' % (site, nxt, STEAM_SVG))
    return tpl.replace("<!--BODY-->", body).encode("utf-8")


def make_handler(admin, port_ref, users_file="", allow_hosts=(), tunnel_hosts=(), web_secret="", web_admins="", site_url="https://twelve-weeks.com"):
    _so = urlparse(site_url)
    csp = CSP + "; frame-src 'self' %s://%s" % (_so.scheme or "https", _so.netloc) if _so.netloc else CSP     # PATCH NOTES embeds the website's news editor
    fails = {}      # client ip -> (count, first fail time): crude brute-force lock (10 fails / 10 min)
    bgdir = os.path.join(admin.launcher_dir, "bg") if admin.launcher_dir else ""
    launcher_root = os.path.dirname(admin.launcher_dir) if admin.launcher_dir else ""     # release/launcher: the CLAN page reuses its scripts, styles and assets as they are

    class H(BaseHTTPRequestHandler):
        server_version = "t2r-admin/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def client_ip(self):
            return self.client_address[0]

        def via_tunnel(self):
            """A request the Cloudflare tunnel (cloudflared on this box) forwards arrives from loopback with the public Host
            (--tunnel-host, e.g. admin.twelve-weeks.com). It is an internet visitor, NOT local use: it must log in like a LAN client."""
            h = (self.headers.get("Host") or "").lower().split(":")[0]
            return bool(tunnel_hosts) and h in tunnel_hosts and self.client_address[0] in ("127.0.0.1", "::1")

        def is_loopback(self):
            if self.via_tunnel():
                return False
            try:
                return ipaddress.ip_address(self.client_ip().split("%")[0]).is_loopback
            except ValueError:
                return False

        def host_ok(self):
            if self.via_tunnel():
                return True
            h = (self.headers.get("Host") or "").lower()
            if self.is_loopback():      # the SSH tunnel / local use: strict, as always (DNS rebinding)
                return h in ("127.0.0.1:%d" % port_ref[0], "localhost:%d" % port_ref[0], "[::1]:%d" % port_ref[0])
            name, _, port = h.rpartition(":")
            if not name or port != str(port_ref[0]):
                return False
            if name in allow_hosts:
                return True
            try:
                ipaddress.ip_address(name.strip("[]"))      # a literal IP in the URL (LAN address): no DNS involved
                return True
            except ValueError:
                return False

        def admin_origin(self):
            """https origin of this panel for the Steam `next` link: the tunnel host it was reached on, else the first --tunnel-host, else admin.<site host>."""
            h = (self.headers.get("Host") or "").lower().split(":")[0]
            if self.via_tunnel():
                return "https://" + h
            if tunnel_hosts:
                return "https://" + tunnel_hosts[0]
            return "https://admin." + (urlparse(site_url).hostname or "twelve-weeks.com")

        def send_gate(self, code, kind, sid=0):
            self.send_bytes(code, gate_page(kind, site_url, self.admin_origin(), sid), "text/html; charset=utf-8")

        def auth_ok(self):
            """Loopback clients (the SSH tunnel; ssh login is their auth) pass. Everyone else (LAN, or the Cloudflare tunnel) needs either a website
            session cookie (tw_s) of a Steam id listed in web-admins.txt, or HTTP Basic credentials matching a line of the users file. Otherwise:
            a styled login page (401, no WWW-Authenticate: no browser dialog) / JSON 401 for the API; /login-token = the HTTP Basic fallback."""
            self.ident = None
            path = urlparse(self.path).path
            if self.is_loopback():
                self.ident = ("local", "")
                return True
            if path in PUBLIC_PATHS:
                return True
            ip = self.client_ip()
            if self.via_tunnel():       # the visitor's own address (Cloudflare sets it) keys the failed-login counter; no LAN-only rule
                ip = (self.headers.get("Cf-Connecting-Ip") or "tunnel").strip()
            try:
                if not self.via_tunnel() and not ipaddress.ip_address(ip.split("%")[0]).is_private:
                    self.send_bytes(403, b"LAN only", "text/plain")
                    return False
            except ValueError:
                self.send_bytes(403, b"LAN only", "text/plain")
                return False
            hdr = self.headers.get("Authorization", "")
            basic = hdr.lower().startswith("basic ")
            if not basic:
                sid = cookie_sid(self.headers.get("Cookie"), load_web_secret(web_secret))
                if sid:
                    if sid in load_web_admins(web_admins):
                        self.ident = ("steam", sid)
                        return True
                    self.send_gate(403, "notadmin", sid)
                    return False
            cnt, t0 = fails.get(ip, (0, 0.0))
            if cnt >= 10 and time.time() - t0 < 600:
                self.send_bytes(429, b"too many failed logins, wait 10 minutes", "text/plain")
                return False
            ok = False
            user = ""
            if basic:
                try:
                    user, _, pw = base64.b64decode(hdr[6:]).decode("utf-8").partition(":")
                    want = load_users(users_file).get(user)
                    ok = bool(want) and hmac.compare_digest(want.encode(), pw.encode())
                except Exception:   # noqa: BLE001
                    ok = False
            if ok:
                fails.pop(ip, None)
                self.ident = ("token", user)
                return True
            if hdr:
                fails[ip] = (cnt + 1 if time.time() - t0 < 600 else 1, t0 if cnt and time.time() - t0 < 600 else time.time())
                time.sleep(1.0)
            if hdr or path == "/login-token":    # the token fallback: the only 401 that asks the browser for a user name + password
                self.send_bytes(401, b"login required", "text/plain", {"WWW-Authenticate": 'Basic realm="T2R admin", charset="UTF-8"'})
            elif path.startswith("/api/"):
                self.send_bytes(401, b'{"error": "login required"}', "application/json; charset=utf-8")
            else:
                self.send_gate(401, "login")
            return False

        def send_bytes(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", csp)
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
            self.send_header("Content-Security-Policy", csp)
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

        def srv(self):
            """The Admin for this request: the test server's when the page's LIVE / TEST switch set the cookie tw_srv=test, else live."""
            t = getattr(admin, "test", None)
            if t is None:
                return admin
            c = self.headers.get("Cookie") or ""
            return t if re.search(r"(?:^|;\s*)tw_srv=test(?:;|$)", c) else admin

        def whoami(self):
            kind, who = self.ident or ("local", "")
            r = {"kind": kind, "id": str(who) if kind == "steam" else "", "name": who if kind == "token" else "", "logout": "", "site": site_url.rstrip("/")}
            if kind == "steam":
                r["logout"] = site_url.rstrip("/") + "/auth/logout"
                try:
                    for pl in admin.players_all(str(who)).get("players", []):
                        if str(pl.get("steamid")) == str(who) and pl.get("name"):
                            r["name"] = pl["name"]
                            break
                except Exception:   # noqa: BLE001
                    pass
            return r

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self.host_ok():
                return self.send_bytes(403, b"bad host", "text/plain")
            if urlparse(self.path).path in ("/icon.png", "/favicon.ico"):   # tab icon, also on the login page
                return self.static(urlparse(self.path).path[1:])
            if not self.auth_ok():
                return
            A = self.srv()
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            p = u.path
            try:
                if p == "/login-token":      # reached only after a good HTTP Basic login
                    return self.send_bytes(302, b"", "text/plain", {"Location": "/"})
                if p == "/api/whoami":
                    return self.json(self.whoami())
                if p == "/api/server":       # the LIVE / TEST switch
                    return self.json({"server": "test" if A is not admin else "live", "test": getattr(admin, "test", None) is not None})
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
                    return self.json(A.overview())
                if p == "/api/online":
                    return self.json(A.players_online())
                if p == "/api/players":
                    return self.json(A.players_all(q.get("q", "")))
                if p == "/api/player":
                    return self.json(A.player(q.get("id", "")))
                if p == "/api/notices":
                    return self.json(A.notices())
                if p == "/api/matches":
                    return self.json(A.matches())
                if p == "/api/teams":
                    return self.json(A.teams())
                if p == "/api/clanview":
                    return self.json(A.clanview(q.get("id", ""), q.get("lang", "en")))
                if p == "/api/clans":
                    return self.json(A.clans())
                if p == "/api/reports":
                    return self.json(A.reports_list())
                if p == "/api/clan-backups":
                    return self.json(A.clan_backups(q.get("id", "")))
                if p == "/api/report":
                    return self.json(A.report(q.get("code", "")))
                if p == "/api/report-file":
                    r = A.report_file(q.get("code", ""), q.get("name", ""))
                    return self.json(r) if r else self.json({"error": "no such file"}, 404)
                if p == "/api/report-image":
                    r = A.report_image(q.get("code", ""), q.get("name", ""))
                    return self.send_bytes(200, r[1], r[0], {"Content-Disposition": "inline", "Cache-Control": "private, max-age=3600"}) if r else self.send_bytes(404, b"no such image", "text/plain")
                if p == "/api/report-video":
                    r = A.report_video(q.get("code", ""), q.get("name", ""))
                    return self.send_range(r[0], r[1], r[2]) if r else self.send_bytes(404, b"no such video", "text/plain")
                if p == "/api/news":
                    return self.json(admin.news_get())
                if p == "/api/logs":
                    return self.json(A.logs(q.get("q", ""), q.get("level", "all"), q.get("file", "0"), min(int(q.get("n", "300") or 300), 1000),
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
            if not self.auth_ok():
                return
            A = self.srv()
            # CSRF: only the page's own script (custom header + same origin) may write
            origin = self.headers.get("Origin")
            host = (self.headers.get("Host") or "").lower()
            if self.headers.get("X-Admin-Request") != "1" or (origin and urlparse(origin).netloc.lower() != host):
                return self.json({"ok": False, "error": "forbidden"}, 403)
            if self.via_tunnel() or (self.ident or ("",))[0] == "steam":    # public / cookie login: the Origin must be present, and over the tunnel be this panel on https
                if not origin or (self.via_tunnel() and origin.lower() != "https://" + host):
                    return self.json({"ok": False, "error": "forbidden"}, 403)
            try:
                p = urlparse(self.path).path
                n = min(int(self.headers.get("Content-Length") or 0), 2 << 20 if p == "/api/news" else 8192)
                body = json.loads(self.rfile.read(n) or b"{}")
                if p == "/api/news":
                    return self.json(admin.news_save(body.get("entries")))
                if p == "/api/ban":       # a ban button on every player (writes <db dir>/bans.txt, the daemon re-reads it)
                    who = self.whoami()
                    return self.json(A.ban(str(body.get("id", "")), str(body.get("reason") or ""), who.get("name") or who.get("id") or who.get("kind", "")))
                if p == "/api/unban":
                    who = self.whoami()
                    return self.json(A.unban(str(body.get("id", "")), who.get("name") or who.get("id") or who.get("kind", "")))
                if p == "/api/kick":
                    return self.json(A.kick(str(body.get("pid", "")), str(body.get("reason") or "")))
                if p == "/api/clan-reset":
                    return self.json(A.clan_reset(str(body.get("id", "")), str(body.get("confirm", "")), bool(body.get("names", False))))
                if p == "/api/clan-restore":
                    return self.json(A.clan_restore(str(body.get("id", "")), str(body.get("file", ""))))
                if p == "/api/notice":
                    return self.json(A.notice_send(str(body.get("text", "")), float(body.get("seconds", 8) or 8)))
                if p == "/api/notice-clear":
                    return self.json(A.notice_clear(int(body.get("id", -1))))
                if p == "/api/shutdown":
                    return self.json(A.shutdown_schedule(float(body.get("minutes", 5)), str(body.get("reason", "")), bool(body.get("restart", True))))
                if p == "/api/shutdown-cancel":
                    return self.json(A.shutdown_cancel())
                if p == "/api/teams":
                    return self.json(A.teams_set(str(body.get("rules", ""))))
                if p == "/api/teams-move":
                    return self.json(A.teams_move(str(body.get("pid", ""))))
                if p == "/api/report-handled":
                    return self.json(A.mark_handled(str(body.get("code", "")), bool(body.get("handled", True))))
                return self.json({"ok": False, "error": "unknown action"}, 404)
            except (ValueError, TypeError):
                return self.json({"ok": False, "error": "bad request"}, 400)
            except Exception as e:    # noqa: BLE001
                return self.json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)

    return H


def make_server(admin, port=7010, bind="127.0.0.1", users_file="", allow_hosts=(), tunnel_hosts=(), web_secret="", web_admins="", site_url="https://twelve-weeks.com"):
    ref = [port]
    srv = ThreadingHTTPServer((bind, port), make_handler(admin, ref, users_file, tuple(h.lower() for h in allow_hosts), tuple(h.lower() for h in tunnel_hosts),
                                                         web_secret, web_admins, site_url))
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
    ap.add_argument("--bind", default="127.0.0.1", help="address to listen on; 0.0.0.0 (or the LAN IP) lets the LAN in, but only with a login from --users (loopback stays login-free)")
    ap.add_argument("--users", default="", help="login file, one 'name token' per line (default <db dir>/admin-users.txt); LAN clients use name:token via HTTP Basic")
    ap.add_argument("--tunnel-host", action="append", default=[], help="public host name a Cloudflare tunnel forwards from loopback (e.g. admin.twelve-weeks.com); those requests must log in")
    ap.add_argument("--allow-host", action="append", default=[], help="extra Host header name accepted from the LAN (besides literal IPs), e.g. pi.local")
    ap.add_argument("--web-secret", default="", help="the website's session secret (default <db dir>/web-secret): validates the tw_s Steam login cookie")
    ap.add_argument("--web-admins", default="", help="Steam64 ids allowed in (default <db dir>/web-admins.txt, one per line, re-read on change; same list as the website's news editors)")
    ap.add_argument("--test-db", default="", help="the TEST server's t2r.db: the page header gets a LIVE / TEST switch")
    ap.add_argument("--test-admin-url", default="http://127.0.0.1:7111", help="the test daemon's loopback admin listener")
    ap.add_argument("--test-daemon-log", default="", help="the test daemon's daemon.log")
    ap.add_argument("--test-daemon", default="127.0.0.1:7101", help="host:port of the test server's game port")
    ap.add_argument("--site-url", default="https://twelve-weeks.com", help="public website: the 'Log in with Steam' link goes to <site-url>/auth/steam?next=https://admin.<host>/")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.db):
        sys.exit("database not found: " + a.db)
    admin = Admin(a.db, a.daemon_log, a.reports, a.daemon, a.status_file, a.admin_url, "", a.update_data, default_launcher_dir())
    if a.test_db and os.path.isfile(a.test_db):     # same reports / patch notes, the test daemon, DB, log and admin secret (<test db dir>/admin-secret.txt)
        admin.test = Admin(a.test_db, a.test_daemon_log, a.reports, a.test_daemon, "", a.test_admin_url, "", a.update_data, default_launcher_dir())
        print("test server switch: db %s, admin %s" % (a.test_db, a.test_admin_url), flush=True)
    ddir = os.path.dirname(os.path.abspath(a.db))
    srv = make_server(admin, a.port, a.bind, a.users or os.path.join(ddir, "admin-users.txt"), a.allow_host, a.tunnel_host,
                      a.web_secret or os.path.join(ddir, "web-secret"), a.web_admins or os.path.join(ddir, "web-admins.txt"), a.site_url)
    print("Twelve Weeks admin site: http://%s:%d/   (db %s, read-only; LAN logins from %s)" % (a.bind, srv.server_address[1], a.db,
          a.users or os.path.join(os.path.dirname(os.path.abspath(a.db)), "admin-users.txt")), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
