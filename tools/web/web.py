#!/usr/bin/env python3
"""twelve-weeks.com: the public website and its read-only API (stdlib only).

  python tools/web/web.py --db <t2r.db> --news <news.json> --site site --public-url https://twelve-weeks.com [--port 7020]

Serves the static site (site/) and:
  GET /api/news                       news.json (the launcher's news), internal fields dropped
  GET /api/me                         {loggedIn, player?}  (Steam session cookie)
  GET /api/players?q=<name>           name search, max 20
  GET /api/player?id=<public id>      profile: stats + clan
  GET /api/leaderboard?by=<board>     top 50; board = elo (team Elo, 10+ matches) | kd (10+ tracked matches) | wins
  Career kills / deaths / downs / favourite weapon come from the daemon's pstats / pweapon tables (booked per match report).
  GET /auth/steam                     Steam OpenID 2.0 sign-in (redirect)
  GET /auth/steam/return              Steam callback: verifies with Steam, sets the session cookie
  GET /auth/logout
  Admins (Steam ids in <db dir>/web-admins.txt, one per line, # comments, re-read on change) can edit the news on /news.html:
  GET /api/admin/news                 raw posts + csrf token + icon / media file lists (admin only)
  POST /api/admin/news                {action: create|update|delete|big, id?, post?, big?} + header X-CSRF (admin only; same origin; JSON)
  Dev only: T2R_WEB_DEV_ADMIN=<steamid> with --host 127.0.0.1 makes GET /auth/dev-login sign that Steam id in as an admin.

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
import math
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
import news_admin  # noqa: E402  (news editing: validation, atomic write, backups)
import clan_view  # noqa: E402  (read-only clan JSON, same as the launcher's CLAN tab)

STEAM_OPENID = "https://steamcommunity.com/openid/login"
CLAIMED_RE = re.compile(r"^https://steamcommunity\.com/openid/id/(7656\d{13})$")
PID_RE = re.compile(r"^(s7656\d{13}|p[0-9a-f]{16})$")
SESSION_DAYS = 30
CACHE_S = 60
MIN_RATE_MATCHES = 10
BOARDS = ("elo", "kd", "wins")
NEWS_KEEP = ("id", "date", "build", "kind", "headline", "title", "body", "text", "sections", "blocks", "big")
CAREER = ("kills", "execs", "revives", "headshots", "marked", "downs", "deaths", "streak", "reports")
# daemon CLAN_WEAPONS index -> (icon key in site/assets/weapons, display name)
WEAPONS = (None, ("bow", "Bow"), ("revolver", "Revolver"), ("shorty", "Shorty"), ("hunting", "Hunting rifle"), ("semi", "Semi-auto rifle"),
           ("burst", "Burst rifle"), ("pistol", "9mm pistol"), ("crossbow", "Crossbow"), ("melee", "Melee"), ("bomb", "Bomb"), ("molotov", "Molotov"))
# 10 ranks = the in-game rank (tools/clan.py rank_of): the chalk symbol = finished 12-week runs (runs_won, rank 1 + one per run,
# clamped to the 10th), the number beside it = weeks survived in total (days_total // 7).
# Rank N shows portrait <look>-<N-1>.png (site/assets/portraits, tools/models/portraits4/rank_cast.py): every MP player look
# (tools/features/dc_data_patches.py FACTION_LOOKS / FEMALE_LOOKS, the base look names without -backpack), by faction and sex
PORTRAIT_LOOKS = {
    ("wlf", "m"): ("militia-male-11", "militia-male-08", "militia-male-12", "militia-male-05", "militia-male-13", "militia-male-14"),
    ("wlf", "f"): ("militia-female-13", "militia-female-12"),
    ("sera", "m"): ("scar-male-13", "scar-male-01", "scar-male-12", "scar-male-06", "scar-male-09", "scar-male-02"),
    ("sera", "f"): ("scar-female-11", "scar-female-09"),
}
RANK_MAX = 10
RUN_DAYS = 83                  # a run is won on day 83 (clan.WIN_DAY)
RANK_NAMES = ("Fresh", "Rookie", "Scrapper", "Survivor", "Blooded", "Seasoned", "Veteran", "Hunter", "Hardened", "Ghost")

A = None          # argparse namespace
SECRET = b""
DEV_ADMIN = 0     # T2R_WEB_DEV_ADMIN, only honoured on a loopback --host
_admins = {"mtime": None, "ids": set()}
ADMIN_BODY_MAX = 300_000


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


def admin_ids():
    """Steam ids in <db dir>/web-admins.txt (one per line, # comments); re-read when the file changes."""
    f = os.path.join(os.path.dirname(os.path.abspath(A.db)), "web-admins.txt")
    try:
        mt = os.stat(f).st_mtime_ns
    except OSError:
        _admins.update(mtime=None, ids=set())
        return _admins["ids"]
    if mt != _admins["mtime"]:
        ids = set()
        for line in open(f, encoding="utf-8", errors="ignore"):
            e = line.split("#", 1)[0].strip()
            if e.isdigit():
                ids.add(int(e))
        _admins.update(mtime=mt, ids=ids)
    return _admins["ids"]


def is_admin(sid):
    return bool(sid) and (sid in admin_ids() or bool(DEV_ADMIN and sid == DEV_ADMIN))


def csrf_for(mac):
    return hmac.new(SECRET, ("csrf." + mac).encode(), hashlib.sha256).hexdigest()


def log_admin(sid, line):
    msg = "%s admin %d: %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), sid, line)
    sys.stderr.write(msg + "\n")
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(A.db)), "web-admin.log"), "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except OSError:
        pass


def asset_files(sub, exts):
    d = os.path.join(os.path.abspath(A.site), "assets", "news", sub)
    try:
        return sorted(f for f in os.listdir(d) if f.lower().endswith(exts) and not f.startswith((".", "_")))
    except OSError:
        return []


def pid_for(token, steamid):
    return "s%d" % steamid if steamid else "p" + hashlib.sha256(token.encode()).hexdigest()[:16]


_cache = {"t": 0, "players": {}}
_lock = threading.Lock()


STATS_TRACKED = [False]          # the daemon books per-match combat stats (pstats); off on an older live daemon
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
            clans = {r["token_id"]: dict(r) for r in c.execute("SELECT * FROM clans")}
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            # career totals the daemon books per match report (daemon.book_career_stats); absent on an older daemon
            pst = {r["token"]: dict(r) for r in c.execute("SELECT * FROM pstats")} if "pstats" in tables else {}
            STATS_TRACKED[0] = "pstats" in tables
            pwp = {}
            if "pweapon" in tables:
                for r in c.execute("SELECT token, weapon, n FROM pweapon"):
                    pwp.setdefault(r["token"], {})[int(r["weapon"])] = int(r["n"])
            elo = {r["key"]: (float(r["elo"]), int(r["n"] or 0)) for r in c.execute("SELECT key, elo, n FROM ratings")} if "ratings" in tables else {}
        finally:
            c.close()
        for r in rows:
            tok, sid = r["token"] or "", int(r["steamid"] or 0)
            pid = pid_for(tok, sid)
            p = out.setdefault(pid, {"id": pid, "steam": bool(sid), "steamid": sid, "name": "", "seen": 0, "kills": 0, "deaths": 0,
                                     "wins": 0, "matches": 0, "draws": 0, "banned": False, "keys": [], "career": dict.fromkeys(CAREER, 0),
                                     "weapons": {}})
            for k in ("wins", "matches", "draws"):
                p[k] += int(r[k] or 0)
            cs = pst.get(tok)
            if cs:
                for k in CAREER:
                    p["career"][k] = max(p["career"][k], int(cs[k] or 0)) if k == "streak" else p["career"][k] + int(cs[k] or 0)
            for w, n in pwp.get(tok, {}).items():
                p["weapons"][w] = p["weapons"].get(w, 0) + n
            seen = float(r["last_seen"] or 0)
            if seen >= p["seen"]:
                p["seen"] = seen
                p["name"] = names.get("s:%d" % sid) if sid and names.get("s:%d" % sid) else (r["name"] or p["name"])
            p["keys"].append(tok[40:64].lower())
            if tok.lower() in btoks or (sid and str(sid) in ids) or (r["name"] or "").lower() in bnames:
                p["banned"] = True
        tw = sum(p["wins"] for p in out.values()); tm = sum(p["matches"] for p in out.values())
        p0 = min(0.9, max(0.1, tw / tm)) if tm else 0.4                   # pool win rate = 1000 (daemon.elo_pool_rate)
        for p in out.values():
            if p["name"].lower() in bnames:
                p["banned"] = True
            ck = "s:%d" % p["steamid"] if p["steamid"] and "s:%d" % p["steamid"] in clans else next((k for k in p["keys"] if k in clans), None)
            p["clanKey"] = ck
            cl = clans.get(ck) if ck else None
            p["weeks"] = int(cl["weeks_total"]) if cl else 0
            p["runsWon"] = int(cl["runs_won"]) if cl else 0
            p["runsLost"] = int(cl.get("runs_lost") or 0) if cl else 0
            p["clanDay"] = int(cl.get("day") or 0) if cl else 0
            p["daysTotal"] = int(cl.get("days_total") or 0) if cl else 0
            p["clanStatus"] = int(cl.get("status") or 0) if cl else 0
            if cl and cl.get("days_total") is not None:
                p["weeks"] = p["daysTotal"] // 7                      # the game's rank number (clan.rank_of)
            p["faction"] = int(cl["faction"]) if cl else 0
            p["winRate"] = round(100 * p["wins"] / p["matches"]) if p["matches"] else 0
            p["kills"], p["deaths"] = p["career"]["kills"], p["career"]["deaths"]
            p["kd"] = round(p["kills"] / p["deaths"], 2) if p["deaths"] else float(p["kills"])
            # team Elo (daemon.elo_update), keyed like the daemon: Steam id, else the install token id; no row yet = the daemon's seed
            # (pool-centred win rate with a 40-match prior). Shown = Elo - 200 / sqrt(matches + 1): few matches rank lower (daemon.elo_shown)
            er = elo.get("s%d" % p["steamid"]) if p["steamid"] else next((elo["t" + k] for k in p["keys"] if "t" + k in elo), None)
            if er:
                e = er[0]
            else:
                wr = (p["wins"] + 0.5 * p["draws"] + 40 * p0) / (p["matches"] + 40)
                e = 1000 + 400 * math.log10((wr / (1 - wr)) / (p0 / (1 - p0)))
            p["elo"] = round(e - 200 / math.sqrt(p["matches"] + 1))
        _cache.update(t=time.time(), players=out)
        return out


def public(p, full=False):
    o = {"id": p["id"], "name": p["name"] or "Survivor", "steam": p["steam"], "wins": p["wins"], "matches": p["matches"], "draws": p["draws"],
         "losses": max(0, p["matches"] - p["wins"] - p["draws"]), "winRate": p["winRate"], "weeks": p["weeks"], "runsWon": p["runsWon"],
         "faction": {1: "WLF", 2: "SERAPHITES"}.get(p["faction"], ""), "elo": p["elo"], "kd": p["kd"], "kills": p["kills"], "deaths": p["deaths"],
         "lastSeen": time.strftime("%Y-%m-%d", time.gmtime(p["seen"])) if p["seen"] else ""}
    if p["steam"]:
        o["steamProfile"] = "https://steamcommunity.com/profiles/%d" % p["steamid"]
    o["rank"] = rank_of(p)
    if full:
        o["clan"] = clan_public(p["clanKey"]) if p["clanKey"] else {"hasClan": False}
        cr = p["career"]
        o["career"] = dict(cr, kd=round(cr["kills"] / cr["deaths"], 2) if cr["deaths"] else float(cr["kills"]), tracked=cr["reports"])
        o["statsTracked"] = STATS_TRACKED[0]
        fav = max(p["weapons"].items(), key=lambda kv: kv[1]) if p["weapons"] else None
        o["favWeapon"] = {"key": WEAPONS[fav[0]][0], "name": WEAPONS[fav[0]][1], "matches": fav[1]} if fav and 0 < fav[0] < len(WEAPONS) else None
        # portrait: the clan's faction (WLF / Seraphites); without a clan a stable pick from the id. The sex and the look are stable
        # picks from the id (the daemon does not know which character the player wears)
        hv = int(hashlib.sha256(p["id"].encode()).hexdigest()[:8], 16)
        fac = {1: "wlf", 2: "sera"}.get(p["faction"]) or ("wlf" if hv & 1 else "sera")
        pool = PORTRAIT_LOOKS[(fac, "f" if hv & 2 else "m")]
        pp = "/assets/portraits/%s-%d.png" % (pool[(hv >> 2) % len(pool)], o["rank"]["tier"])
        o["portrait"] = pp + "?v=%d" % ver(os.path.join(A.site, pp.lstrip("/")))
    return o


def rank_of(p):
    """The in-game rank (tools/clan.py rank_of): rank 1 + one per finished 12-week run (max 10), weeks = weeks survived in total.
    day = how far the living clan's run is (the next rank comes when it is won); next = None at the top rank."""
    lvl = min(RANK_MAX, p.get("runsWon", 0) + 1)
    alive = p.get("clanStatus") == 1
    return {"level": lvl, "tier": lvl - 1, "title": RANK_NAMES[lvl - 1], "max": RANK_MAX, "runs": p.get("runsWon", 0), "weeks": p.get("weeks", 0),
            "alive": alive, "day": min(RUN_DAYS, p.get("clanDay", 0)) if alive else 0, "runDays": RUN_DAYS, "next": lvl + 1 if lvl < RANK_MAX else None}


def clan_public(key):
    v = clan_view.view(A.db, None, key=key)
    keep = ("hasClan", "factionName", "status", "daysDone", "daysTotal", "weeksTotal", "size", "healthy", "hungry", "sick", "maxSize",
            "runsWon", "runsLost", "week", "dayOfWeek", "weeks", "event", "mission", "boosters", "lastMatch")
    return {k: v[k] for k in keep if k in v} if v.get("ok") else {"hasClan": False}


def leaderboard(by):
    ps = [p for p in players().values() if not p["banned"] and p["matches"] > 0]
    if by == "elo":
        ps = [p for p in ps if p["matches"] >= MIN_RATE_MATCHES]
    if by == "kd":                     # K/D from the matches the daemon tracked (pstats), at least MIN_RATE_MATCHES of them
        ps = [p for p in ps if p["career"]["reports"] >= MIN_RATE_MATCHES]
    ps.sort(key=lambda p: (p[by], p["matches"]), reverse=True)
    return [dict(public(p), rank=i + 1) for i, p in enumerate(ps[:50])]


def news():
    try:
        items = json.load(open(A.news, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    try:            # site/news-big.json: the milestone posts (new maps, big overhauls) shown as BIG UPDATES
        big = set(json.load(open(os.path.join(A.site, "news-big.json"), encoding="utf-8")).get("ids", []))
    except (OSError, ValueError, AttributeError):
        big = set()
    out = []
    for n in items if isinstance(items, list) else []:
        if isinstance(n, dict):
            o = {k: n[k] for k in NEWS_KEEP if k in n}
            o["big"] = bool(n["big"]) if "big" in n else n.get("id") in big     # an explicit "big" (set by the site's editor) wins over news-big.json
            out.append(o)
    return out[:60]


def news_raw():
    """Every post with all its fields (for the editor); big resolved like news()."""
    try:
        items = news_admin.load(A.news)
    except (OSError, ValueError, news_admin.Invalid):
        return []
    pub = {str(n.get("id")): n["big"] for n in news()}
    return [dict(n, big=pub.get(str(n.get("id")), bool(n.get("big")))) for n in items if isinstance(n, dict)]


# ---------------------------------------------------------------- session
def sign(sid, exp):
    return hmac.new(SECRET, ("%s.%d" % (sid, exp)).encode(), hashlib.sha256).hexdigest()


def session_info(cookie_header):
    """(steam id, cookie mac) of a valid session cookie, else (None, None)."""
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "tw_s":
            try:
                sid, exp, mac = v.split(".")
                if int(exp) > time.time() and hmac.compare_digest(mac, sign(sid, int(exp))) and sid.isdigit():
                    return int(sid), mac
            except ValueError:
                return None, None
    return None, None


def session_sid(cookie_header):
    return session_info(cookie_header)[0]


DEFAULT_NEXT = ("https://admin.twelve-weeks.com",)


def next_origins():
    """Origins (https://host) a login may send the visitor back to: --allow-next (default the admin panel), each a subdomain of the public host."""
    return tuple(o.rstrip("/").lower() for o in (getattr(A, "allow_next", None) or DEFAULT_NEXT))


def valid_next(url):
    """The `next` of /auth/steam: exactly an https URL whose origin is in --allow-next and a subdomain of the public host.
    No userinfo, no port, no backslash / control chars, path must start with a single '/'. Anything else -> None (never an open redirect)."""
    if not isinstance(url, str) or not url or len(url) > 300 or any(ord(ch) < 33 or ord(ch) > 126 for ch in url) or "\\" in url or "%" in url:
        return None
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    pub = (urllib.parse.urlsplit(A.public_url).hostname or "").lower()
    try:
        host, port = (u.hostname or "").lower(), u.port
    except ValueError:
        return None
    if u.scheme != "https" or "@" in u.netloc or port is not None or u.username or u.password or not host or u.netloc.lower() != host:
        return None
    if not pub or not host.endswith("." + pub) or ("https://" + host) not in next_origins():
        return None
    if u.path.startswith("//") or (u.path and not u.path.startswith("/")) or u.fragment:
        return None
    return url


def cookie_domain():
    """Domain= for the session cookie so admin.<host> gets it too: the public host when it has a dot and is not an IP / localhost."""
    h = (urllib.parse.urlsplit(A.public_url).hostname or "").lower()
    if "." not in h or re.match(r"^[0-9.]+$", h) or ":" in h:
        return ""
    return h


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
    q = {k: v for k, v in params.items() if k.startswith("openid.")}      # (our own `next` is not part of the OpenID message)
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

    def _cookie(self, value, max_age, domain=None):
        secure = "; Secure" if A.public_url.startswith("https://") else ""
        d = cookie_domain() if domain is None else domain
        return "tw_s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s%s" % (value, max_age, secure, "; Domain=" + d if d else "")

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
                return self._json({"loggedIn": True, "id": "s%d" % sid, "player": public(pl, True) if pl else None, "admin": is_admin(sid)})
            if p == "/api/admin/news":
                sid, mac = session_info(self.headers.get("Cookie"))
                if not is_admin(sid):
                    return self._json({"error": "admin only"}, 403)
                return self._json({"csrf": csrf_for(mac), "posts": news_raw(), "icons": asset_files("", (".png",)),
                                   "media": asset_files("media", (".gif", ".webp", ".png", ".jpg", ".jpeg", ".mp4", ".webm")),
                                   "kinds": list(news_admin.KINDS)})
            if p == "/auth/dev-login" and DEV_ADMIN:
                exp = int(time.time()) + 86400
                return self._redirect("/news.html", [self._cookie("%d.%d.%s" % (DEV_ADMIN, exp, sign(DEV_ADMIN, exp)), 86400)])
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
                by = q.get("by", "elo")
                if by not in BOARDS:
                    return self._json({"error": "unknown board"}, 400)
                return self._json({"by": by, "minMatches": MIN_RATE_MATCHES if by in ("elo", "kd") else 1, "rows": leaderboard(by), "statsTracked": STATS_TRACKED[0]}, cache="public, max-age=60")
            if p == "/auth/steam":
                ret = A.public_url + "/auth/steam/return"
                nxt = valid_next(q.get("next", "")) if q.get("next") else None
                if nxt:
                    ret += "?" + urllib.parse.urlencode({"next": nxt})
                params = {"openid.ns": "http://specs.openid.net/auth/2.0", "openid.mode": "checkid_setup", "openid.return_to": ret,
                          "openid.realm": A.public_url + "/", "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
                          "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"}
                return self._redirect(STEAM_OPENID + "?" + urllib.parse.urlencode(params))
            if p == "/auth/steam/return":
                sid = steam_verify(q)
                if not sid:
                    return self._redirect("/?login=failed")
                exp = int(time.time()) + SESSION_DAYS * 86400
                # `next` is read from the signed openid.return_to (Steam verified it), validated again, and must equal the plain param
                rt = urllib.parse.parse_qs(urllib.parse.urlsplit(q.get("openid.return_to", "")).query).get("next", [""])[0]
                nxt = valid_next(rt) if rt and rt == q.get("next") else None
                return self._redirect(nxt or "/player.html?id=s%d" % sid, [self._cookie("%d.%d.%s" % (sid, exp, sign(sid, exp)), SESSION_DAYS * 86400)])
            if p == "/auth/logout":
                return self._redirect("/", [self._cookie("", 0), self._cookie("", 0, domain="")])      # (Domain cookie + any old host-only one)
            return self._static(p)
        except sqlite3.Error as e:
            return self._json({"error": "database unavailable", "detail": str(e)[:120]}, 503)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        if p != "/api/admin/news":
            return self._json({"error": "not found"}, 404)
        sid, mac = session_info(self.headers.get("Cookie"))
        if not is_admin(sid):
            return self._json({"error": "admin only"}, 403)
        origin = self.headers.get("Origin", "")
        host = (self.headers.get("Host") or "").split(":")[0]
        okorigin = {A.public_url}
        if host in ("127.0.0.1", "localhost") and A.host in ("127.0.0.1", "localhost"):
            okorigin.add("http://" + self.headers.get("Host", ""))
        if origin not in okorigin:
            return self._json({"error": "bad origin"}, 403)
        if not hmac.compare_digest(self.headers.get("X-CSRF", ""), csrf_for(mac)):
            return self._json({"error": "bad csrf token (reload the page)"}, 403)
        if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
            return self._json({"error": "json only"}, 415)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n <= 0 or n > ADMIN_BODY_MAX:
            return self._json({"error": "body size"}, 413)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("body")
        except (ValueError, UnicodeDecodeError):
            return self._json({"error": "bad json"}, 400)
        try:
            res, line = news_admin.apply(A.news, body.get("action"), "%d" % sid, pid=body.get("id"), post=body.get("post"), big=body.get("big"))
        except news_admin.Invalid as e:
            return self._json({"error": str(e)}, 400)
        except OSError as e:
            return self._json({"error": "could not write the news file", "detail": e.__class__.__name__}, 500)
        log_admin(sid, line)
        res["posts"] = news_raw()
        return self._json(res)

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
        cache = "public, max-age=86400" if "/assets/" in f.replace("\\", "/") else "no-cache"   # pages / css / js: revalidate (an update shows at once)
        if f.endswith((".mp4", ".webm")):          # feature clips: byte ranges (Safari / iOS will not play a video whose server ignores Range)
            return self._media(f, ctype, cache)
        body = open(f, "rb").read()
        if f.endswith(".html"):     # Cloudflare edge + browser caches keep style.css / *.js for hours: version them by file time
            body = VER_RE.sub(lambda m: m.group(1) + m.group(2) + "?v=%d" % ver(os.path.join(root, m.group(2))) + m.group(3), body.decode("utf-8")).encode("utf-8")
        extra = [("Content-Security-Policy", "frame-ancestors 'self' " + " ".join(next_origins()))] if f.endswith(".html") else None   # the admin panel embeds news.html
        return self._send(200, body, ctype, extra, cache=cache)

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


VER_RE = re.compile(r'((?:href|src)=")([a-z0-9_-]+\.(?:css|js))(")')


def ver(path):
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0


def main():
    global A, SECRET, DEV_ADMIN
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--news", required=True)
    ap.add_argument("--site", default=os.path.join(HERE, "..", "..", "site"))
    ap.add_argument("--public-url", default="https://twelve-weeks.com")
    ap.add_argument("--allow-next", action="append", default=[], help="https origin a Steam login may redirect to afterwards (repeatable; default https://admin.twelve-weeks.com)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7020)
    A = ap.parse_args()
    A.public_url = A.public_url.rstrip("/")
    A.allow_next = [o.rstrip("/") for o in (A.allow_next or list(DEFAULT_NEXT))]
    sec = os.path.join(os.path.dirname(os.path.abspath(A.db)), "web-secret")
    if not os.path.exists(sec):
        with open(sec, "w") as fh:
            fh.write(secrets.token_hex(32))
        try:
            os.chmod(sec, 0o600)
        except OSError:
            pass
    SECRET = open(sec).read().strip().encode()
    dev = os.environ.get("T2R_WEB_DEV_ADMIN", "").strip()
    if dev.isdigit() and A.host == "127.0.0.1":
        DEV_ADMIN = int(dev)
        print("DEV ADMIN on: /auth/dev-login signs in Steam id %s as admin (loopback only)" % dev, flush=True)
    print("twelve-weeks web on %s:%d (public %s)" % (A.host, A.port, A.public_url), flush=True)
    ThreadingHTTPServer((A.host, A.port), H).serve_forever()


if __name__ == "__main__":
    main()
