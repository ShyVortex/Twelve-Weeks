"""Bug reports from the launcher (POST /report): validation, rate limit, safe extraction, storage.

A report is ONE zip (Content-Type application/zip): `meta.json` (what happened, when, map, version, name, steam id ...) + `files/<name>` (logs, crash
dumps, system info, optional files/screenshot-N.<png|jpg|webp|gif|bmp>). It is stored under <reports>/<UTC date-time>_<code>_<player>/ as meta.json (client meta + server fields) + files/ (the zip
entries, written byte for byte; nothing is executed or marked executable; names are reduced to a flat safe file name, so a zip-slip path never
leaves the report folder). Nothing is readable over HTTP. Read them with tools/update_server/reports.py.
"""
import hmac
import io
import json
import os
import re
import secrets
import shutil
import threading
import time
import zipfile
from collections import defaultdict, deque

MAX_BODY = 80 * 1024 * 1024            # the whole zip
MAX_ENTRIES = 60
MAX_ENTRY = 256 * 1024 * 1024          # one file, unpacked (a crash dump is ~125 MB)
MAX_UNPACKED = 600 * 1024 * 1024       # all files together, unpacked (zip-bomb guard)
RATE_N, RATE_WINDOW = 30, 3600         # reports per IP per hour (the earlier limit blocked a player mid-session; the size cap per report still applies)
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"   # no 0/O/1/I
TEXT_FIELDS = {"text": 4000, "when": 200, "whenText": 400, "mapMode": 100, "version": 60, "name": 40, "nameSource": 60, "steamId": 30,
               "launcherVersion": 30, "os": 200, "gpu": 300, "game": 200}
SAFE = re.compile(r"[^A-Za-z0-9._-]")
# Optional screenshots (launcher 0.1.13): zip entries files/screenshot-<n>.<ext>. Anything with that name must be a real png/jpg/webp/gif/bmp
# (magic bytes decide, not the extension), <= 8 MB each, <= 5 files; otherwise the whole report is refused (400/413).
SHOT_RE = re.compile(r"^screenshot-([1-9][0-9]?)\.(png|jpg|jpeg|webp|gif|bmp)$", re.I)
SHOT_MAX_FILES, SHOT_MAX_EACH = 5, 8 * 1024 * 1024
# Optional video clips (launcher 0.1.13): sent AFTER the report zip, one raw streamed PUT per clip (PUT /report-clip), so a 200 MB clip is never held in
# memory on either side. The zip response carries a per-report clipKey; only that key can attach clips to that report.
CLIP_MAX_FILES, CLIP_MAX_EACH, CLIP_MAX_TOTAL = 2, 200 * 1024 * 1024, 250 * 1024 * 1024
CLIP_TYPES = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm", "mkv": "video/x-matroska"}
DISK_MAX_BYTES = int(os.environ.get("T2R_REPORTS_MAX_GB", "20")) * (1 << 30)       # clips refused when the reports folder is bigger
DISK_MIN_FREE = int(os.environ.get("T2R_REPORTS_MIN_FREE_GB", "10")) * (1 << 30)   # ... or the disk has less free space
CLIP_RATE_N = 3                                                                    # reports with clips per IP per hour
SHOT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp"}


def sniff_image(head):
    """First bytes -> 'png'|'jpg'|'webp'|'gif'|'bmp' or None."""
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == bytes((255, 216, 255)):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:2] == b"BM" and len(head) >= 14:
        return "bmp"
    return None


def sniff_video(head):
    """First bytes -> 'mp4'|'mov'|'webm'|'mkv' or None (ISO-BMFF 'ftyp' box, or EBML header with the doctype)."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mov" if head[8:12] == b"qt  " else "mp4"
    if head[:4] == bytes((0x1A, 0x45, 0xDF, 0xA3)):
        return "webm" if b"webm" in head[:64] else "mkv"
    return None


def folder_size(root):
    n = 0
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            try:
                n += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return n


def disk_ok(root, extra=0):
    """False when clips must be refused: the reports folder is over its cap or the disk is nearly full (text/logs are still accepted)."""
    try:
        os.makedirs(root, exist_ok=True)
        if folder_size(root) + extra > DISK_MAX_BYTES:
            return False
        return shutil.disk_usage(root).free - extra >= DISK_MIN_FREE
    except OSError:
        return False


class ReportError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


class RateLimiter:
    def __init__(self, n=RATE_N, window=RATE_WINDOW, clock=time.time):
        self.n, self.window, self.clock, self.hits, self.lock = n, window, clock, defaultdict(deque), threading.Lock()

    def allow(self, ip):
        now = self.clock()
        with self.lock:
            if len(self.hits) > 2048:       # one deque per source address ever seen otherwise
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] > self.window]:
                    del self.hits[k]
            q = self.hits[ip]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.n:
                return False
            q.append(now)
            return True


def flat_name(name):
    """Any zip entry name -> one safe file name (no directories, no dots-only, bounded)."""
    base = re.split(r"[\\/]", name)[-1]
    base = SAFE.sub("_", base).strip(".") or "file"
    return base[:80]


def new_code(root):
    for _ in range(50):
        code = "R-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        if not any(("_%s_" % code) in d for d in os.listdir(root)):
            return code
    raise ReportError(500, "could not allocate a report code")


def save_report(root, body, ip="", now=None, clip_limiter=None):
    """Validate + store one report. Returns {"code", "dir"}. Raises ReportError(status, message)."""
    if len(body) > MAX_BODY:
        raise ReportError(413, "report too large")
    try:
        z = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile:
        raise ReportError(400, "not a zip file")
    infos = z.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ReportError(400, "too many files")
    if sum(i.file_size for i in infos) > MAX_UNPACKED or any(i.file_size > MAX_ENTRY for i in infos):
        raise ReportError(413, "unpacked size too large")
    try:
        meta_raw = z.read("meta.json")
        meta_in = json.loads(meta_raw.decode("utf-8"))
        if not isinstance(meta_in, dict):
            raise ValueError
    except (KeyError, ValueError, UnicodeDecodeError):
        raise ReportError(400, "meta.json missing or not an object")
    meta = {}
    for k, lim in TEXT_FIELDS.items():
        v = meta_in.get(k, "")
        meta[k] = (v if isinstance(v, str) else str(v))[:lim]
    if len(meta["text"].strip()) < 5:
        raise ReportError(400, "the description is missing")
    meta["includeDumps"] = bool(meta_in.get("includeDumps"))
    try:
        want_clips = max(0, min(CLIP_MAX_FILES, int(meta_in.get("clips") or 0)))
    except (TypeError, ValueError):
        want_clips = 0
    clip_refused = ""
    if want_clips:
        if clip_limiter is not None and not clip_limiter.allow(ip):
            clip_refused = "too many reports with video clips from this address, try again later"
        elif not disk_ok(root):
            clip_refused = "the server cannot take video clips right now (storage is full)"
        if clip_refused:
            want_clips = 0
    meta["clipsExpected"] = want_clips
    if want_clips:
        meta["clipKey"] = secrets.token_hex(16)
    os.makedirs(root, exist_ok=True)
    code = new_code(root)
    t = time.gmtime(now or time.time())
    player = SAFE.sub("_", meta["name"])[:15] or "player"
    d = os.path.join(root, "%s_%s_%s" % (time.strftime("%Y%m%d-%H%M%S", t), code, player))
    os.makedirs(os.path.join(d, "files"))
    try:
        res = _store(z, infos, d, meta, code, t, ip)
        res["clipKey"] = meta.get("clipKey", "")
        res["clipRefused"] = clip_refused
        return res
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)      # a refused / failed report leaves no half folder behind (meta.json is written last)
        raise


def _store(z, infos, d, meta, code, t, ip):
    used, files = set(), []
    total = 0
    shots = 0
    for i in infos:
        if i.is_dir() or i.filename == "meta.json":
            continue
        if (i.external_attr >> 16) & 0o170000 == 0o120000:      # a symlink entry: skipped
            continue
        name = flat_name(i.filename)
        shot = SHOT_RE.match(name)
        if shot:
            shots += 1
            if shots > SHOT_MAX_FILES:
                raise ReportError(400, "too many screenshots (max %d)" % SHOT_MAX_FILES)
            if i.file_size > SHOT_MAX_EACH:
                raise ReportError(413, "screenshot too large (max %d MB each)" % (SHOT_MAX_EACH >> 20))
        base, n = name, 1
        while name in used:
            n += 1
            name = "%d_%s" % (n, base)
        used.add(name)
        with z.open(i) as src, open(os.path.join(d, "files", name), "wb") as dst:
            left = MAX_ENTRY
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                left -= len(chunk)
                total += len(chunk)
                if left < 0:
                    raise ReportError(413, "entry too large")
                if total > MAX_UNPACKED:
                    raise ReportError(413, "unpacked size too large")
                dst.write(chunk)
        entry = {"name": name, "size": os.path.getsize(os.path.join(d, "files", name)), "zipName": i.filename[:200]}
        if shot:
            fp = os.path.join(d, "files", name)
            with open(fp, "rb") as fh:
                kind = sniff_image(fh.read(16))
            if not kind or entry["size"] > SHOT_MAX_EACH:
                raise ReportError(400, "%s is not a valid png/jpg/webp/gif/bmp image (max %d MB)" % (name, SHOT_MAX_EACH >> 20))
            want = "jpg" if shot.group(2).lower() == "jpeg" else shot.group(2).lower()
            if kind != want:                       # the content decides: store under the real extension
                newn = "screenshot-%s.%s" % (shot.group(1), kind)
                while newn in used:
                    newn = "x" + newn
                os.replace(fp, os.path.join(d, "files", newn))
                used.discard(name); used.add(newn)
                entry["name"] = newn
            entry["kind"] = "screenshot"
            entry["contentType"] = SHOT_TYPES[kind]
        files.append(entry)
    meta.update(code=code, received=time.strftime("%Y-%m-%dT%H:%M:%SZ", t), ip=ip, files=files, handled=False)
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    return {"code": code, "dir": d}


_clip_lock = threading.Lock()


def find_report_dir(root, code):
    if not re.match(r"^R-[A-Z0-9]{4}$", code or ""):
        return None
    try:
        for n in os.listdir(root):
            if ("_%s_" % code) in n and os.path.isfile(os.path.join(root, n, "meta.json")):
                return os.path.join(root, n)
    except OSError:
        pass
    return None


def save_clip(root, code, key, length, rfile, ip=""):
    """Attach one video clip to an existing report. `rfile` is read in 1 MB pieces straight to disk with a running byte counter (never buffered whole);
    `length` is the declared Content-Length, checked before a byte is read. Returns {"name","size"}. Raises ReportError."""
    d = find_report_dir(root, code)
    if not d:
        raise ReportError(404, "no such report")
    if length <= 0:
        raise ReportError(400, "empty clip")
    if length > CLIP_MAX_EACH:
        raise ReportError(413, "Clip too big - trim it to under %d MB" % (CLIP_MAX_EACH >> 20))
    with _clip_lock:
        with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        if not meta.get("clipKey") or not hmac.compare_digest(str(key or ""), meta["clipKey"]):
            raise ReportError(403, "bad clip key")
        have = [x for x in meta.get("files", []) if x.get("kind") == "video"]
        pending = int(meta.get("clipsExpected") or 0)
        if len(have) >= min(CLIP_MAX_FILES, pending):
            raise ReportError(400, "too many clips for this report (max %d)" % CLIP_MAX_FILES)
        if sum(x["size"] for x in have) + length > CLIP_MAX_TOTAL:
            raise ReportError(413, "clips together too big (max %d MB)" % (CLIP_MAX_TOTAL >> 20))
        if not disk_ok(root, length):
            raise ReportError(507, "the server cannot take video clips right now (storage is full)")
        tmp = os.path.join(d, "files", ".clip-%s.part" % secrets.token_hex(4))
    got = 0
    try:
        with open(tmp, "wb") as out:
            first = rfile.read(min(64, length))
            kind = sniff_video(first)
            if not kind:
                raise ReportError(400, "not a valid mp4/mov/webm/mkv video")
            out.write(first)
            got = len(first)
            while got < length:
                chunk = rfile.read(min(1 << 20, length - got))
                if not chunk:
                    break
                got += len(chunk)
                if got > CLIP_MAX_EACH:
                    raise ReportError(413, "Clip too big - trim it to under %d MB" % (CLIP_MAX_EACH >> 20))
                out.write(chunk)
        if got != length:
            raise ReportError(400, "short upload")
        with _clip_lock:
            with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            have = [x for x in meta.get("files", []) if x.get("kind") == "video"]
            if len(have) >= CLIP_MAX_FILES or sum(x["size"] for x in have) + got > CLIP_MAX_TOTAL:
                raise ReportError(413, "clips together too big")
            name = "clip-%d.%s" % (len(have) + 1, kind)
            os.replace(tmp, os.path.join(d, "files", name))
            meta.setdefault("files", []).append({"name": name, "size": got, "kind": "video", "contentType": CLIP_TYPES[kind], "zipName": ""})
            mp = os.path.join(d, "meta.json")
            with open(mp + ".tmp", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=1, ensure_ascii=False)
            os.replace(mp + ".tmp", mp)
        return {"name": name, "size": got}
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
