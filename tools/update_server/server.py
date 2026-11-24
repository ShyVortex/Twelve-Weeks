#!/usr/bin/env python3
"""T2R update/file server for the launcher (stdlib only).

  python tools/update_server/server.py --data <dir> [--port 7002] [--public-url https://host:port]
         [--status-file <daemon status json>] [--daemon host:port]

Endpoints (see README.md):
  GET /manifest.json?channel=stable[&version=X]   {version, channel, files:[{path,size,sha256,url}], launcher:{version,url,sha256}}
  GET /files/<sha256>[.gz|.br]                     content-addressed blob (or its compressed twin, raw bytes, no Content-Encoding), HTTP Range supported
  GET /part1-maps.json, /part1-files/<sha256>      TEMPORARY Part I map pack for playtesters (part1_maps.py, publish_part1.py); never in /manifest.json
  GET /news.json                                   <data>/news.json (or [])
  GET /status.json                                 {online, server_version, matches, ...}
  GET /versions.json?channel=stable                all published versions (rollback)
  POST /report                                     one zip (meta.json + files/) -> reports/<date>_<code>_<player>/ ; see report_store.py, reports.py
  GET /clan.json?player=<install id>               read-only clan view from the daemon's t2r.db (--db)
  GET /clanfeed.json?player=<id>[&limit=30&since=<id>&lang=pl]  read-only clan feed (tools/clan_story.py) + camp roster, same --db
"""
import argparse
import json
import os
import re
import socket
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import report_store
import daemon_lines
import part1_maps

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ZBLOB_RE = re.compile(r"^([0-9a-f]{64})\.(gz|br)$")            # compressed blob next to the raw one, see publish.py
ZEXT = {"gzip": "gz", "br": "br"}
NAME_RE = re.compile(r"^[A-Za-z0-9._+-]{1,40}$")


class Store:
    """<data>/blobs/<sha256>, <data>/manifests/<channel>/<version>.json, <data>/channels.json {channel: version},
    <data>/launcher.json {version, sha256, file}, <data>/news.json."""

    def __init__(self, data):
        self.data = os.path.abspath(data)
        self.blobs = os.path.join(self.data, "blobs")
        os.makedirs(self.blobs, exist_ok=True)
        os.makedirs(os.path.join(self.data, "manifests"), exist_ok=True)

    def read_json(self, name, default):
        # Windows: publish.py replaces channels.json / a manifest with os.replace; a reader that opens it in that instant gets PermissionError.
        # A missing file is final (default), anything else is retried briefly: it must not turn into a 404 "no such channel" for a client.
        p = os.path.join(self.data, name)
        for i in range(8):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                return default
            except (OSError, ValueError):
                if i == 7:
                    return default
                time.sleep(0.02 * (i + 1))
        return default

    def current(self, channel):
        return self.read_json("channels.json", {}).get(channel)

    def versions(self, channel):
        if not NAME_RE.match(channel or ""):
            return []
        d = os.path.join(self.data, "manifests", channel)
        try:
            names = [n[:-5] for n in os.listdir(d) if n.endswith(".json")]
        except OSError:
            return []
        def mt(n):
            try:
                return os.path.getmtime(os.path.join(d, n + ".json"))
            except OSError:               # removed between listdir and stat
                return 0
        return sorted(names, key=mt)

    def manifest(self, channel, version=None):
        if not NAME_RE.match(channel or ""):
            return None
        version = version or self.current(channel)
        if not version or not NAME_RE.match(version):
            return None
        return self.read_json(os.path.join("manifests", channel, version + ".json"), None)

    def blob_path(self, sha):
        if SHA_RE.match(sha or "") or ZBLOB_RE.match(sha or ""):
            return os.path.join(self.blobs, sha)
        return None


def parse_range(header, size):
    """Returns (start, end_inclusive), None (no/ignored header) or 'bad' (416). Single range only."""
    if not header:
        return None
    m = re.match(r"^bytes=(\d*)-(\d*)$", header.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    a, b = m.group(1), m.group(2)
    if not a:                                  # suffix: last N bytes
        n = int(b)
        if n == 0 or size == 0:
            return "bad"
        return (max(0, size - n), size - 1)
    start = int(a)
    end = int(b) if b else size - 1
    if start >= size or end < start:
        return "bad"
    return (start, min(end, size - 1))


def make_handler(store, public_url, status_file, daemon_addr, db_path="", reports_dir=""):
    limiter = report_store.RateLimiter()
    clip_limiter = report_store.RateLimiter(report_store.CLIP_RATE_N, report_store.RATE_WINDOW)
    status_cache = {"t": 0.0, "v": None}

    def daemon_probe():
        """No status file: ask the daemon the version question the launcher asks (op 0xB0); reachable = online."""
        try:
            with socket.create_connection(daemon_addr, timeout=3) as c:
                c.settimeout(2)
                payload = bytes([1]) + b"0"
                c.sendall((len(payload) + 1).to_bytes(2, "little") + b"\xb0" + payload)
                r = c.recv(1024)
            m = re.search(rb"server=(\S+)", r)
            return {"online": True, "server_version": m.group(1).decode() if m else "", "matches": None}
        except OSError:
            return {"online": False, "server_version": "", "matches": None}

    def get_status():
        now = time.time()
        if status_cache["v"] is not None and now - status_cache["t"] < 3:
            return status_cache["v"]
        if status_file:
            try:
                with open(status_file, encoding="utf-8") as f:
                    d = json.load(f)
                age = now - float(d.get("ts", 0))
                v = {"online": age < 30, "server_version": d.get("server_version", ""), "matches": d.get("matches"),
                     "players_online": d.get("players_online"), "queue": d.get("queue"),
                     "notices": d.get("notices") or [], "target_version": d.get("target_version", ""),
                     "roster": d.get("roster") or []}      # [{name, state, map, party}]: names + states only (launcher players panel, test feature)
            except (OSError, ValueError):
                v = {"online": False, "server_version": "", "matches": None}
        elif daemon_addr:
            v = daemon_probe()
        else:
            v = {"online": False, "server_version": "", "matches": None}
        status_cache.update(t=now, v=v)
        return v

    class H(BaseHTTPRequestHandler):
        timeout = 30                      # per-socket-operation idle limit: a stalled / slowloris client frees its thread (was: for ever)
        server_version = "t2r-update/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *a):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))

        def _json(self, obj, code=200, head=False):
            body = json.dumps(obj, separators=(",", ":")).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                if not head:
                    self.wfile.write(body)
            except OSError:               # the client went away (reset / timeout): nothing to answer, no traceback
                self.close_connection = True

        def _ip(self):
            """The caller's address. Behind a loopback front (tools/files-rs t2r-files, or a Cloudflare tunnel) every peer is loopback and
            the visitor's address is in CF-Connecting-IP; a loopback caller without it is a local tool."""
            ip = self.client_address[0]
            if ip in ("127.0.0.1", "::1"):
                ip = (self.headers.get("CF-Connecting-IP") or "").strip() or ip
            return ip

        def _base(self):
            if public_url:
                return public_url.rstrip("/")
            # Behind an HTTPS reverse proxy (443 -> file front -> here) the links must say https://, else a client that fetched the manifest
            # over https is handed http://<host>/files/... (port 80 = a redirect only). Trusted only from a loopback peer.
            proto = "http"
            if self.client_address[0] in ("127.0.0.1", "::1") and (self.headers.get("X-Forwarded-Proto") or "").strip().lower() == "https":
                proto = "https"
            return proto + "://" + (self.headers.get("Host") or "localhost")

        def _route(self, head):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            p = u.path
            if p == "/manifest.json":
                ch = (q.get("channel") or ["stable"])[0]
                m = store.manifest(ch, (q.get("version") or [None])[0])
                if not m:
                    return self._json({"error": "no such channel/version"}, 404, head)
                m = json.loads(json.dumps(m))
                # a manifest that names a blob the server does not have (a publish still copying, a blob removed by hand) would send every client
                # into a 404 half-way through its download: answer "try again" instead, before the first byte
                remote = lambda f: str(f.get("url", "")).startswith("https://")
                gone = [f["path"] for f in m.get("files", []) if not remote(f) and not os.path.isfile(os.path.join(store.blobs, f["sha256"]))]
                if gone:
                    sys.stderr.write("manifest %s/%s: %d blob(s) missing (%s ...)\n" % (ch, m.get("version"), len(gone), gone[0]))
                    return self._json({"error": "this version is not fully published yet, try again in a minute"}, 503, head)
                base = self._base()
                for f in m["files"]:
                    if remote(f):
                        continue
                    f["url"] = base + "/files/" + f["sha256"]
                    ext = ZEXT.get(f.get("enc"))
                    if ext and f.get("zsize") and os.path.isfile(os.path.join(store.blobs, f["sha256"] + "." + ext)):
                        f["zurl"] = base + "/files/%s.%s" % (f["sha256"], ext)
                    else:
                        f.pop("zsize", None)
                        f.pop("enc", None)
                def launcher_entry(name):
                    la = store.read_json(name, None)
                    if not la:
                        return None
                    url = la.get("url") if str(la.get("url", "")).startswith("https://") else base + "/files/" + la["sha256"]
                    return {"version": la["version"], "sha256": la["sha256"], "size": la.get("size"), "url": url}
                m["launcher"] = launcher_entry("launcher.json")
                m["launcher_linux"] = launcher_entry("launcher-linux.json")
                return self._json(m, 200, head)
            if p == "/news.json":
                return self._json(store.read_json("news.json", []), 200, head)
            if p == "/status.json":
                return self._json(get_status(), 200, head)
            if p == "/clan.json":
                if not db_path:
                    return self._json({"ok": False, "error": "no database configured (--db)"}, 503, head)
                import clan_view
                return self._json(clan_view.view(db_path, (q.get("player") or [""])[0]), 200, head)
            if p == "/clanfeed.json":
                if not db_path:
                    return self._json({"ok": False, "error": "no database configured (--db)"}, 503, head)
                import clanfeed_view
                return self._json(clanfeed_view.view(db_path, (q.get("player") or [""])[0], (q.get("limit") or ["30"])[0],
                                                     (q.get("since") or ["0"])[0], (q.get("lang") or ["en"])[0]), 200, head)
            if p == "/versions.json":
                ch = (q.get("channel") or ["stable"])[0]
                return self._json({"channel": ch, "current": store.current(ch), "versions": store.versions(ch)}, 200, head)
            if p.startswith("/files/"):
                return self._file(p[7:], head)
            if p.startswith("/media/"):           # news media (GIF / WebP / PNG / JPG / MP4 / WebM named in a news entry's blocks), <data>/media/<name>
                return self._media(p[7:], head)
            if p.startswith("/download/"):
                return self._download(p[10:], head)
            if p == "/part1-maps.json":           # TEMPORARY playtester pack, separate from the release manifest (part1_maps.py)
                pm = part1_maps.public(store.data, self._base())
                if not pm:
                    return self._json({"error": "no Part I map pack published"}, 404, head)
                return self._json(pm, 200, head)
            if p.startswith("/part1-files/"):
                return self._file(p[13:], head, part1_maps.blob_path(store.data, p[13:]))
            return self._json({"error": "not found"}, 404, head)

        MEDIA_TYPES = {"gif": "image/gif", "webp": "image/webp", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                       "mp4": "video/mp4", "webm": "video/webm"}

        def _media(self, name, head):
            m = re.match(r"^([A-Za-z0-9_-][A-Za-z0-9_.-]{0,80})\.([A-Za-z0-9]{3,4})$", name)
            ctype = m and self.MEDIA_TYPES.get(m.group(2).lower())
            path = os.path.join(store.data, "media", name)
            if not ctype or not os.path.isfile(path) or os.path.getsize(path) > 6 << 20:
                return self._json({"error": "no such file"}, 404, head)
            try:
                fh = open(path, "rb")
            except OSError:
                return self._json({"error": "no such file"}, 404, head)
            with fh:
                self._media_headers = (ctype, "public, max-age=86400")
                return self._file_open(fh, path, "m-%d-%d" % (int(os.path.getmtime(path)), os.path.getsize(path)), head)

        def _file(self, sha, head, path=None):
            path = path or store.blob_path(sha)
            if not path or not os.path.isfile(path):
                return self._json({"error": "no such file"}, 404, head)
            try:
                fh = open(path, "rb")             # opened first: a blob removed by a gc right now is a clean 404, not a half-sent answer
            except OSError:
                return self._json({"error": "no such file"}, 404, head)
            with fh:
                return self._file_open(fh, path, sha, head)

        def _download(self, name, head):
            # named launcher downloads for Discord #files; downloads.json {"<file name>": "<blob sha256>"}
            from urllib.parse import unquote
            name = unquote(name)
            sha = store.read_json("downloads.json", {}).get(name)
            path = store.blob_path(sha) if sha else None
            if not path or not os.path.isfile(path):
                return self._json({"error": "no such download"}, 404, head)
            try:
                fh = open(path, "rb")
            except OSError:
                return self._json({"error": "no such download"}, 404, head)
            with fh:
                return self._file_open(fh, path, sha, head, name)

        def _file_open(self, fh, path, sha, head, name=None):
            size = os.fstat(fh.fileno()).st_size
            rng = parse_range(self.headers.get("Range"), size)
            if rng == "bad":
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end = rng if rng else (0, size - 1)
            self.send_response(206 if rng else 200)
            mh = getattr(self, "_media_headers", None)
            self._media_headers = None
            self.send_header("Content-Type", mh[0] if mh else "application/octet-stream")
            if mh:
                self.send_header("Cache-Control", mh[1])
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", '"%s"' % sha)
            if name:
                self.send_header("Content-Disposition", 'attachment; filename="%s"' % name.replace('"', ""))
            self.send_header("Content-Length", str(end - start + 1 if size else 0))
            if rng:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.end_headers()
            if head or not size:
                return
            left = end - start + 1
            fh.seek(start)
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except OSError:
                    self.close_connection = True
                    return
                left -= len(chunk)
            if left > 0:                      # the file shrank under us: a short body must not look like a complete one
                self.close_connection = True

        def do_PUT(self):
            u = urlparse(self.path)
            if u.path != "/report-clip":
                return self._json({"error": "not found"}, 404)
            if not reports_dir:
                return self._json({"ok": False, "error": "reports are not enabled on this server"}, 503)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0 or n > report_store.CLIP_MAX_EACH:       # refused on the header alone: the body is never read
                self.close_connection = True
                return self._json({"ok": False, "error": "Clip too big - trim it to under %d MB" % (report_store.CLIP_MAX_EACH >> 20) if n > 0 else "empty clip"}, 413 if n > 0 else 400)
            try:
                r = report_store.save_clip(reports_dir, q.get("code", ""), q.get("key", ""), n, self.rfile, self._ip())
            except report_store.ReportError as e:
                self.close_connection = True
                return self._json({"ok": False, "error": e.msg}, e.status)
            except OSError:               # idle timeout / reset mid-upload
                self.close_connection = True
                return
            sys.stderr.write("report %s clip %s (%d bytes)\n" % (q.get("code", ""), r["name"], r["size"]))
            return self._json({"ok": True, "name": r["name"], "size": r["size"]})

        def do_POST(self):
            u = urlparse(self.path)
            if u.path != "/report":
                return self._json({"error": "not found"}, 404)
            if not reports_dir:
                return self._json({"ok": False, "error": "reports are not enabled on this server"}, 503)
            ip = self._ip()
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0 or n > report_store.MAX_BODY:
                self.close_connection = True
                return self._json({"ok": False, "error": "bad size (max %d MB)" % (report_store.MAX_BODY >> 20)}, 413 if n > 0 else 400)
            if not limiter.allow(ip):
                self.close_connection = True
                return self._json({"ok": False, "error": "too many reports, try again later"}, 429)
            body = bytearray()
            try:
                while len(body) < n:
                    chunk = self.rfile.read(min(1 << 20, n - len(body)))
                    if not chunk:
                        break
                    body += chunk
            except OSError:               # idle timeout / reset mid-upload
                self.close_connection = True
                return
            if len(body) != n:
                return self._json({"ok": False, "error": "short body"}, 400)
            try:
                r = report_store.save_report(reports_dir, bytes(body), ip, clip_limiter=clip_limiter)
            except report_store.ReportError as e:
                return self._json({"ok": False, "error": e.msg}, e.status)
            sys.stderr.write("report %s stored in %s\n" % (r["code"], r["dir"]))
            daemon_lines.snapshot_later(r["dir"])      # the player's daemon log lines next to the report (the log rotates away in ~90 min)
            return self._json({"ok": True, "code": r["code"], "clipKey": r["clipKey"], "clipRefused": r["clipRefused"]})

        def do_GET(self):
            self._route(False)

        def do_HEAD(self):
            self._route(True)

    return H


BIND_RETRY_S = float(os.environ.get("T2R_BIND_RETRY_S", "30"))


class Srv(ThreadingHTTPServer):
    request_queue_size = 128              # default 5: a burst of launchers (release day, tunnel reconnect) overflowed the accept backlog
    daemon_threads = True
    allow_reuse_address = False           # Windows SO_REUSEADDR = port stealing: a second instance would silently share 7002

    def server_bind(self):
        # exclusive bind (Windows SO_EXCLUSIVEADDRUSE; POSIX SO_REUSEADDR only rebinds over TIME_WAIT) + bounded retry: a restart
        # right after a kill can see the port busy for a few seconds. Still taken after BIND_RETRY_S -> OSError (main exits 3).
        s = self.socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        elif os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        t0 = time.monotonic(); deadline = t0 + BIND_RETRY_S; nxt = t0 + 1.0
        while True:
            try:
                s.bind(self.server_address)
                break
            except OSError as e:
                now = time.monotonic()
                if now >= deadline:
                    raise
                if now >= nxt:
                    print("BIND %s:%s busy (%s); retrying for up to %.0fs more" % (self.server_address[0], self.server_address[1], e, deadline - now), flush=True)
                    nxt = now + 5.0
                time.sleep(0.25)
        if time.monotonic() - t0 > 0.3:
            print("BIND %s:%s ok after %.1fs of retries" % (self.server_address[0], self.server_address[1], time.monotonic() - t0), flush=True)
        self.server_address = s.getsockname()
        self.server_name = self.server_address[0]; self.server_port = self.server_address[1]


def make_server(data, host="0.0.0.0", port=7002, public_url="", status_file="", daemon="", db="", reports=None):
    daemon_addr = None
    if daemon:
        h, _, p = daemon.rpartition(":")
        daemon_addr = (h or "127.0.0.1", int(p))
    store = Store(data)
    srv = Srv((host, port), make_handler(store, public_url, status_file, daemon_addr, db, os.path.join(data, "reports") if reports is None else reports))
    srv.daemon_threads = True
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=7002)
    ap.add_argument("--public-url", default="", help="base URL put into manifest file urls (default: the request's Host header)")
    ap.add_argument("--status-file", default="", help="JSON written by the daemon (T2R_STATUS_FILE)")
    ap.add_argument("--daemon", default="", help="host:port of the daemon for a reachability/version probe when there is no status file")
    ap.add_argument("--db", default="", help="the daemon's t2r.db, opened read-only for /clan.json (never written)")
    ap.add_argument("--reports", default=None, help="folder for launcher bug reports (default <data>/reports; empty = POST /report disabled)")
    a = ap.parse_args()
    try:
        srv = make_server(a.data, a.host, a.port, a.public_url, a.status_file, a.daemon, a.db, a.reports)
    except OSError as e:
        print("FATAL update server %s:%d already in use after %.0fs (is another server running?): %s" % (a.host, a.port, BIND_RETRY_S, e), flush=True)
        os._exit(3)
    print("update server on %s:%d, data %s" % (a.host, a.port, os.path.abspath(a.data)))
    if a.reports != "":
        daemon_lines.archive_loop()                   # rotated daemon logs kept gzipped for daemon_lines.ARCHIVE_DAYS days
    srv.serve_forever()


if __name__ == "__main__":
    main()
