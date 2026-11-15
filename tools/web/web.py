#!/usr/bin/env python3
"""twelve-weeks.com: the public website and its read-only API (stdlib only).

  python tools/web/web.py --db <t2r.db> --news <news.json> --site site --public-url https://twelve-weeks.com [--port 7020]

Serves the static site (site/) and:
  GET /api/news                       news.json (the launcher's news), internal fields dropped
  GET /api/me                         {loggedIn, player?}  (Steam session cookie)
  GET /api/players?q=<name>           name search, max 20
  GET /api/player?id=<public id>      profile: stats + clan
  GET /api/leaderboard?by=<board>     top 50; board = wins | winrate | matches | weeks (kills/deaths are not recorded by the daemon yet)
  GET /auth/steam                     Steam OpenID 2.0 sign-in (redirect)
  GET /auth/steam/return              Steam callback: verifies with Steam, sets the session cookie
  GET /auth/logout

Privacy and safety:
- The database is opened read-only (mode=ro); this server never writes it.
- Name tokens are secrets (they log a client in) and never leave this server. A player's public id is the Steam id for Steam
  accounts ("s7656..."), else "p" + the first 16 hex chars of sha256(token).
- Players in bans.txt (next to the database) are left out of search and leaderboards.
- The session cookie only holds the Steam id, an expiry and an HMAC; the key is <db dir>/web-secret (made on first start).
"""
import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "update_server"))
import clan_view  # noqa: E402  (read-only clan JSON, same as the launcher's CLAN tab)

STEAM_OPENID = "https://steamcommunity.com/openid/login"
CLAIMED_RE = re.compile(r"^https://steamcommunity\.com/openid/id/(7656\d{13})$")
PID_RE = re.compile(r"^(s7656\d{13}|p[0-9a-f]{16})$")
SESSION_DAYS = 30
CACHE_S = 60
MIN_RATE_MATCHES = 10
BOARDS = ("wins", "winrate", "matches", "weeks")
NEWS_KEEP = ("id", "date", "build", "kind", "headline", "title", "body", "text", "sections")

A = None          # argparse namespace
SECRET = b""


# ---------------------------------------------------------------- data
def db():
    c = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(A.db).replace("\\", "/"), uri=True, timeout=3)
    c.row_factory = sqlite3.Row
    return c


def load_bans():
    ids, names, toks = set(), set(), set()
    try:
        for line in open(os.path.join(os.path.dirname(os.path.abspath(A.db)), "bans.txt"), encoding="utf-8", errors="ignore"):
            e = line.split("#", 1)[0].strip()
            if not e or e.lower().startswith("hwid:"):
                continue
            if e.lower().startswith("token:"):
                toks.add(e[6:].strip().lower())
            elif e.isdigit():
                ids.add(e)
            else:
                names.add(e.lower())
    except OSError:
        pass
    return ids, names, toks


def pid_for(token, steamid):
    return "s%d" % steamid if steamid else "p" + hashlib.sha256(token.encode()).hexdigest()[:16]


_cache = {"t": 0, "players": {}}
_lock = threading.Lock()


def players():
    """{public id: player dict}, one entry per Steam account (its installs summed) or per non-Steam install. Cached CACHE_S."""
    with _lock:
        if time.time() - _cache["t"] < CACHE_S:
            return _cache["players"]
        ids, bnames, btoks = load_bans()
        out = {}
        c = db()
        try:
            names = {r["token_id"]: (r["name"] or "") for r in c.execute("SELECT token_id, name FROM names")}
            rows = c.execute("SELECT token, name, kills, deaths, wins, matches, draws, steamid, last_seen FROM players").fetchall()
            clans = {r["token_id"]: dict(r) for r in c.execute("SELECT token_id, status, day, weeks_total, runs_won, runs_lost, faction FROM clans")}
        finally:
            c.close()
        for r in rows:
            tok, sid = r["token"] or "", int(r["steamid"] or 0)
            pid = pid_for(tok, sid)
            p = out.setdefault(pid, {"id": pid, "steam": bool(sid), "steamid": sid, "name": "", "seen": 0, "kills": 0, "deaths": 0,
                                     "wins": 0, "matches": 0, "draws": 0, "banned": False, "keys": []})
            for k in ("kills", "deaths", "wins", "matches", "draws"):
                p[k] += int(r[k] or 0)
            seen = float(r["last_seen"] or 0)
            if seen >= p["seen"]:
                p["seen"] = seen
                p["name"] = names.get("s:%d" % sid) if sid and names.get("s:%d" % sid) else (r["name"] or p["name"])
            p["keys"].append(tok[40:64].lower())
            if tok.lower() in btoks or (sid and str(sid) in ids) or (r["name"] or "").lower() in bnames:
                p["banned"] = True
        for p in out.values():
            if p["name"].lower() in bnames:
                p["banned"] = True
            ck = "s:%d" % p["steamid"] if p["steamid"] and "s:%d" % p["steamid"] in clans else next((k for k in p["keys"] if k in clans), None)
            p["clanKey"] = ck
            cl = clans.get(ck) if ck else None
            p["weeks"] = int(cl["weeks_total"]) if cl else 0
            p["runsWon"] = int(cl["runs_won"]) if cl else 0
            p["faction"] = int(cl["faction"]) if cl else 0
            p["winRate"] = round(100 * p["wins"] / p["matches"]) if p["matches"] else 0
        _cache.update(t=time.time(), players=out)
        return out


def public(p, full=False):
    o = {"id": p["id"], "name": p["name"] or "Survivor", "steam": p["steam"], "wins": p["wins"], "matches": p["matches"], "draws": p["draws"],
         "losses": max(0, p["matches"] - p["wins"] - p["draws"]), "winRate": p["winRate"], "weeks": p["weeks"], "runsWon": p["runsWon"],
         "faction": {1: "WLF", 2: "SERAPHITES"}.get(p["faction"], ""),
         "lastSeen": time.strftime("%Y-%m-%d", time.gmtime(p["seen"])) if p["seen"] else ""}
    if p["steam"]:
        o["steamProfile"] = "https://steamcommunity.com/profiles/%d" % p["steamid"]
    if full:
        o["clan"] = clan_public(p["clanKey"]) if p["clanKey"] else {"hasClan": False}
    return o


def clan_public(key):
    v = clan_view.view(A.db, None, key=key)
    keep = ("hasClan", "factionName", "status", "daysDone", "daysTotal", "weeksTotal", "size", "healthy", "hungry", "sick", "maxSize",
            "runsWon", "runsLost", "week", "dayOfWeek", "weeks", "event", "mission", "boosters", "lastMatch")
    return {k: v[k] for k in keep if k in v} if v.get("ok") else {"hasClan": False}


def leaderboard(by):
    ps = [p for p in players().values() if not p["banned"] and p["matches"] > 0]
    if by == "winrate":
        ps = [p for p in ps if p["matches"] >= MIN_RATE_MATCHES]
    key = {"wins": "wins", "winrate": "winRate", "matches": "matches", "weeks": "weeks"}[by]
    if by == "weeks":
        ps = [p for p in ps if p["weeks"] > 0]
    ps.sort(key=lambda p: (p[key], p["matches"]), reverse=True)
    return [dict(public(p), rank=i + 1) for i, p in enumerate(ps[:50])]


def news():
    try:
        items = json.load(open(A.news, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for n in items if isinstance(items, list) else []:
        if isinstance(n, dict):
            out.append({k: n[k] for k in NEWS_KEEP if k in n})
    return out[:30]


# ---------------------------------------------------------------- session
def sign(sid, exp):
    return hmac.new(SECRET, ("%s.%d" % (sid, exp)).encode(), hashlib.sha256).hexdigest()


def session_sid(cookie_header):
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "tw_s":
            try:
                sid, exp, mac = v.split(".")
                if int(exp) > time.time() and hmac.compare_digest(mac, sign(sid, int(exp))) and sid.isdigit():
                    return int(sid)
            except ValueError:
                return None
    return None


def steam_verify(params):
    """Ask Steam whether this OpenID assertion is genuine. Returns the Steam id or None."""
    if params.get("openid.mode") != "id_res":
        return None
    if params.get("openid.op_endpoint") != STEAM_OPENID:
        return None
    if not params.get("openid.return_to", "").startswith(A.public_url + "/auth/steam/return"):
        return None
    m = CLAIMED_RE.match(params.get("openid.claimed_id", ""))
    if not m:
        return None
    q = dict(params)
    q["openid.mode"] = "check_authentication"
    req = urllib.request.Request(STEAM_OPENID, data=urllib.parse.urlencode(q).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "twelve-weeks-web"})
    try:
        body = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
    except OSError:
        return None
    return int(m.group(1)) if "is_valid:true" in body else None


# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    server_version = "twelve-weeks"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % a))

    def _send(self, code, body, ctype, extra=None, cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200, cache="no-store"):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", cache=cache)

    def _redirect(self, url, cookies=()):
        self._send(302, b"", "text/plain", [("Location", url)] + [("Set-Cookie", c) for c in cookies])

    def _cookie(self, value, max_age):
        secure = "; Secure" if A.public_url.startswith("https://") else ""
        return "tw_s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s" % (value, max_age, secure)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        p = u.path
        try:
            if p == "/api/news":
                return self._json(news(), cache="public, max-age=120")
            if p == "/api/me":
                sid = session_sid(self.headers.get("Cookie"))
                if not sid:
                    return self._json({"loggedIn": False})
                pl = players().get("s%d" % sid)
                return self._json({"loggedIn": True, "id": "s%d" % sid, "player": public(pl, True) if pl else None})
            if p == "/api/players":
                s = (q.get("q") or "").strip().lower()[:32]
                if len(s) < 2:
                    return self._json([])
                hits = [pl for pl in players().values() if not pl["banned"] and pl["matches"] > 0 and s in (pl["name"] or "").lower()]
                hits.sort(key=lambda pl: (not (pl["name"] or "").lower().startswith(s), -pl["matches"]))
                return self._json([public(pl) for pl in hits[:20]])
            if p == "/api/player":
                pid = q.get("id", "")
                pl = players().get(pid) if PID_RE.match(pid) else None
                if not pl or pl["banned"]:
                    return self._json({"error": "not found"}, 404)
                return self._json(public(pl, True))
            if p == "/api/leaderboard":
                by = q.get("by", "wins")
                if by not in BOARDS:
                    return self._json({"error": "unknown board"}, 400)
                return self._json({"by": by, "minMatches": MIN_RATE_MATCHES if by == "winrate" else 1, "rows": leaderboard(by)}, cache="public, max-age=60")
            if p == "/auth/steam":
                ret = A.public_url + "/auth/steam/return"
                params = {"openid.ns": "http://specs.openid.net/auth/2.0", "openid.mode": "checkid_setup", "openid.return_to": ret,
                          "openid.realm": A.public_url + "/", "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
                          "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"}
                return self._redirect(STEAM_OPENID + "?" + urllib.parse.urlencode(params))
            if p == "/auth/steam/return":
                sid = steam_verify(q)
                if not sid:
                    return self._redirect("/?login=failed")
                exp = int(time.time()) + SESSION_DAYS * 86400
                return self._redirect("/player.html?id=s%d" % sid, [self._cookie("%d.%d.%s" % (sid, exp, sign(sid, exp)), SESSION_DAYS * 86400)])
            if p == "/auth/logout":
                return self._redirect("/", [self._cookie("", 0)])
            return self._static(p)
        except sqlite3.Error as e:
            return self._json({"error": "database unavailable", "detail": str(e)[:120]}, 503)

    def _static(self, p):
        if p.endswith("/"):
            p += "index.html"
        root = os.path.abspath(A.site)
        f = os.path.abspath(os.path.join(root, urllib.parse.unquote(p).lstrip("/")))
        if not f.startswith(root + os.sep) or not os.path.isfile(f) or os.path.basename(f).startswith(("_", ".")):
            f404 = os.path.join(root, "404.html")
            body = open(f404, "rb").read() if os.path.isfile(f404) else b"Not found"
            return self._send(404, body, "text/html; charset=utf-8")
        ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        cache = "public, max-age=86400" if "/assets/" in f.replace("\\", "/") else "public, max-age=300"
        if f.endswith((".mp4", ".webm")):          # feature clips: byte ranges (Safari / iOS will not play a video whose server ignores Range)
            return self._media(f, ctype, cache)
        return self._send(200, open(f, "rb").read(), ctype, cache=cache)

    def _media(self, f, ctype, cache):
        size = os.path.getsize(f)
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)$", (self.headers.get("Range") or "").strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1)); end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start > end or start >= size:
                self.send_response(416); self.send_header("Content-Range", "bytes */%d" % size); self.send_header("Content-Length", "0"); self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(f, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                b = fh.read(min(65536, left))
                if not b:
                    break
                try:
                    self.wfile.write(b)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(b)


def main():
    global A, SECRET
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--news", required=True)
    ap.add_argument("--site", default=os.path.join(HERE, "..", "..", "site"))
    ap.add_argument("--public-url", default="https://twelve-weeks.com")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7020)
    A = ap.parse_args()
    A.public_url = A.public_url.rstrip("/")
    sec = os.path.join(os.path.dirname(os.path.abspath(A.db)), "web-secret")
    if not os.path.exists(sec):
        with open(sec, "w") as fh:
            fh.write(secrets.token_hex(32))
        try:
            os.chmod(sec, 0o600)
        except OSError:
            pass
    SECRET = open(sec).read().strip().encode()
    print("twelve-weeks web on %s:%d (public %s)" % (A.host, A.port, A.public_url), flush=True)
    ThreadingHTTPServer((A.host, A.port), H).serve_forever()


if __name__ == "__main__":
    main()
