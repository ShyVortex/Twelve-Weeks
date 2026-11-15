"""News editing for the website's admins (stdlib only): schema validation, atomic write, backups, soft delete.

Used by web.py. The news file is the launcher's news.json (a JSON list of posts, newest first). Posts keep every field the editor does not
know (stamp, version, pl, ...) when they are updated. Block types are the ones the launcher and the site render
(heading, text, note, media, stats, sections); anything else is rejected, never silently dropped.
"""
import json
import os
import re
import threading
import time

LOCK = threading.Lock()
KEEP_BACKUPS = 50
KINDS = ("build", "hotfix", "patch", "update")
SEC_KEYS = ("new", "changed", "why", "watch", "known", "fixed")
BLOCK_TYPES = ("heading", "text", "note", "media", "stats", "sections")
MAX_BLOCKS = 80
MAX_POST_BYTES = 120_000
MAX_MD = 10_000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MEDIA_RE = re.compile(r"^(?:media/)?[A-Za-z0-9_-][A-Za-z0-9_.-]{0,80}\.(gif|webp|png|jpe?g|mp4|webm)$", re.I)
ICON_RE = re.compile(r"^(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.png$")
ID_RE = re.compile(r"^\d{1,9}$")


class Invalid(ValueError):
    pass


def _str(v, what, maxlen, required=False):
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise Invalid("%s must be text" % what)
    if len(v) > maxlen:
        raise Invalid("%s is too long (max %d)" % (what, maxlen))
    if "\x00" in v:
        raise Invalid("%s has a control character" % what)
    if required and not v.strip():
        raise Invalid("%s is required" % what)
    return v


def _list(v, what, maxn):
    if v is None:
        return []
    if not isinstance(v, list):
        raise Invalid("%s must be a list" % what)
    if len(v) > maxn:
        raise Invalid("%s has too many entries (max %d)" % (what, maxn))
    return v


def clean_sections(secs, what="sections"):
    if secs is None:
        return {}
    if not isinstance(secs, dict):
        raise Invalid("%s must be an object" % what)
    out = {}
    for k, lines in secs.items():
        if k not in SEC_KEYS:
            raise Invalid("%s: unknown section '%s'" % (what, str(k)[:20]))
        ls = [_str(x, "%s.%s line %d" % (what, k, i + 1), 2000) for i, x in enumerate(_list(lines, what + "." + k, 60))]   # posts already have 500+ character lines
        ls = [x for x in ls if x.strip()]
        if ls:
            out[k] = ls
    return out


def clean_block(b, i, lang_free=False):
    w = "block %d" % (i + 1)
    if not isinstance(b, dict):
        raise Invalid(w + " must be an object")
    t = b.get("type")
    if t not in BLOCK_TYPES:
        raise Invalid("%s: unknown type '%s'" % (w, str(t)[:20]))
    if t == "heading":
        return {"type": t, "text": _str(b.get("text"), w + " text", 200, True)}
    if t == "text":
        return {"type": t, "md": _str(b.get("md"), w + " text", MAX_MD, True)}
    if t == "note":
        return {"type": t, "title": _str(b.get("title"), w + " title", 120), "md": _str(b.get("md"), w + " text", MAX_MD, True)}
    if t == "sections":
        return {"type": t, "sections": clean_sections(b.get("sections"), w)}
    if t == "media":
        items = []
        for it in _list(b.get("items"), w + " items", 3):
            if not isinstance(it, dict):
                raise Invalid(w + ": media item must be an object")
            src = _str(it.get("src"), w + " file name", 90, True)
            if not MEDIA_RE.match(src):
                raise Invalid("%s: bad media file name '%s'" % (w, src[:40]))
            items.append({"src": src, "caption": _str(it.get("caption"), w + " caption", 200)})
        if not items:
            raise Invalid(w + ": media needs at least one file")
        return {"type": t, "items": items}
    # stats
    cols = [_str(c, w + " column", 40) for c in _list(b.get("cols"), w + " columns", 8)]
    if not cols:
        raise Invalid(w + ": stats needs at least one column")
    rows = []
    for r in _list(b.get("rows"), w + " rows", 80):
        if not isinstance(r, dict):
            raise Invalid(w + ": row must be an object")
        icon = _str(r.get("icon"), w + " icon", 80)
        if icon and not ICON_RE.match(icon):
            raise Invalid("%s: bad icon '%s'" % (w, icon[:40]))
        vals = [_str(v, w + " value", 60) for v in _list(r.get("values"), w + " values", 8)]
        if len(vals) > len(cols):
            raise Invalid(w + ": a row has more values than columns")
        rows.append({"icon": icon, "name": _str(r.get("name"), w + " row name", 80), "values": vals + [""] * (len(cols) - len(vals))})
    return {"type": t, "cols": cols, "rows": rows}


def clean_blocks(blocks, what="blocks"):
    return [clean_block(b, i) for i, b in enumerate(_list(blocks, what, MAX_BLOCKS))]


def clean_post(p):
    """Validated editable fields of a post. Raises Invalid. Does not include id or unknown fields."""
    if not isinstance(p, dict):
        raise Invalid("post must be an object")
    out = {"headline": _str(p.get("headline"), "headline", 200, True)}
    date = _str(p.get("date"), "date", 10, True)
    if not DATE_RE.match(date):
        raise Invalid("date must be YYYY-MM-DD")
    try:
        time.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise Invalid("date is not a real date")
    out["date"] = date
    out["build"] = _str(p.get("build"), "build", 16)
    kind = p.get("kind") or "build"
    if kind not in KINDS:
        raise Invalid("kind must be one of " + ", ".join(KINDS))
    out["kind"] = kind
    out["big"] = bool(p.get("big"))
    out["sections"] = clean_sections(p.get("sections"))
    out["blocks"] = clean_blocks(p.get("blocks"))
    pl = p.get("pl")
    if pl is not None:
        if not isinstance(pl, dict):
            raise Invalid("pl must be an object")
        o = {}
        h = _str(pl.get("headline"), "pl headline", 200)
        if h.strip():
            o["headline"] = h
        s = clean_sections(pl.get("sections"), "pl sections")
        if s:
            o["sections"] = s
        b = clean_blocks(pl.get("blocks"), "pl blocks")
        if b:
            o["blocks"] = b
        out["pl"] = o
    if len(json.dumps(out, ensure_ascii=False).encode()) > MAX_POST_BYTES:
        raise Invalid("post is too large")
    return out


# ---------------------------------------------------------------- storage
def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return []
    if not isinstance(d, list):
        raise Invalid("news file is not a list")
    return d


def _atomic(path, obj):
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def backup(path):
    """Timestamped copy of the news file before a write; keeps the newest KEEP_BACKUPS."""
    if not os.path.isfile(path):
        return None
    d = os.path.join(os.path.dirname(os.path.abspath(path)), "news-backups")
    os.makedirs(d, exist_ok=True)
    t = time.time()
    dst = os.path.join(d, "news-%s-%03d.json" % (time.strftime("%Y%m%d-%H%M%S", time.localtime(t)), int((t % 1) * 1000)))
    with open(path, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())
    old = sorted(f for f in os.listdir(d) if f.startswith("news-") and f.endswith(".json"))
    for f in old[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass
    return dst


def _find(items, pid):
    for i, n in enumerate(items):
        if isinstance(n, dict) and str(n.get("id")) == str(pid):
            return i
    return -1


def next_id(items):
    nums = [int(n["id"]) for n in items if isinstance(n, dict) and str(n.get("id", "")).isdigit()]
    return str(max(nums) + 1 if nums else 1)


def apply(path, action, who, pid=None, post=None, big=None):
    """One admin write. Returns (result dict, log line). Raises Invalid. Thread-safe."""
    with LOCK:
        items = load(path)
        if action == "create":
            c = clean_post(post)
            nid = next_id(items)
            ent = {"id": int(nid) if all(isinstance(n.get("id"), int) for n in items if isinstance(n, dict) and "id" in n) else nid}
            ent.update(c)
            items.insert(0, ent)
            what = "create id=%s '%s'" % (nid, c["headline"][:60])
            pid = nid
        elif action == "update":
            i = _find(items, pid)
            if i < 0:
                raise Invalid("no such post")
            c = clean_post(post)
            old = items[i]
            new = dict(old)                      # keeps id, stamp, version, title, body ... that the editor does not touch
            for k in ("sections", "blocks", "pl"):
                new.pop(k, None)
            new.update(c)
            if not c["blocks"]:
                new.pop("blocks", None)
            if "pl" in c and not c["pl"]:
                new.pop("pl", None)
            items[i] = new
            what = "update id=%s '%s'" % (pid, c["headline"][:60])
        elif action == "big":
            i = _find(items, pid)
            if i < 0:
                raise Invalid("no such post")
            items[i]["big"] = bool(big)
            what = "big id=%s %s" % (pid, "on" if big else "off")
        elif action == "delete":
            i = _find(items, pid)
            if i < 0:
                raise Invalid("no such post")
            gone = items.pop(i)
            tp = os.path.join(os.path.dirname(os.path.abspath(path)), "news-trash.json")
            try:
                trash = load(tp)
            except (Invalid, ValueError):
                trash = []
            gone = dict(gone, deletedAt=time.strftime("%Y-%m-%d %H:%M:%S"), deletedBy=who)
            trash.insert(0, gone)
            _atomic(tp, trash)
            what = "delete id=%s '%s' (to news-trash.json)" % (pid, str(gone.get("headline", ""))[:60])
        else:
            raise Invalid("unknown action")
        backup(path)
        _atomic(path, items)
        return {"ok": True, "id": str(pid)}, "%s by %s" % (what, who)
