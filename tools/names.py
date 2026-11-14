"""Custom player names + clan tags (wishlist 8). Imported by daemon.py.

Stored server-side keyed by the token id = token bytes 20..31 (same key as clan.py), so a
rename (or a new T2N name in the token) keeps stats and clan. Display text is "[TAG] name"
(tag 1..5 chars, name 1..15 chars) = at most 23 bytes, fits the 32-byte 0x10 name field, the
0x30 peer-table record and the 0x17 / 0x04 name fields.
Precedence: custom name > Steam name (bridge / token) > Setup name.
"""
import re, time

NAME_MAX = 15
TAG_MAX = 5
_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]*$")
_TAG_OK = re.compile(r"^[A-Za-z0-9]+$")


def token_id(token):
    t = (token or "").lower()
    return t[40:64] if len(t) == 64 else t


def clean(name, tag):
    """-> (name, tag, error). Both empty = clear the custom name. Tag is upper-cased."""
    name = re.sub(r" +", " ", (name or "").strip())
    tag = (tag or "").strip().upper()
    if not name and not tag:
        return "", "", None
    if not name:
        return None, None, "name needed"
    if len(name) > NAME_MAX:
        return None, None, "name too long (max %d)" % NAME_MAX
    if not _NAME_OK.match(name):
        return None, None, "name: letters, digits, space . _ - only"
    if tag and len(tag) > TAG_MAX:
        return None, None, "tag too long (max %d)" % TAG_MAX
    if tag and not _TAG_OK.match(tag):
        return None, None, "tag: letters and digits only"
    return name, tag, None


def init(c):
    c.execute("CREATE TABLE IF NOT EXISTS names(token_id TEXT PRIMARY KEY, name TEXT, tag TEXT, updated REAL)")


def load(c, tid):
    init(c)
    r = c.execute("SELECT name,tag FROM names WHERE token_id=?", (tid,)).fetchone()
    return (r[0] or "", r[1] or "") if r else ("", "")


def save(c, tid, name, tag, taken=None):
    """Validated store; returns (name, tag, error). Empty name+tag deletes the row. taken(name) -> True = another player shows it."""
    name, tag, err = clean(name, tag)
    if err:
        return None, None, err
    if name and taken and taken(name):
        return None, None, "name taken"
    init(c)
    if not name:
        c.execute("DELETE FROM names WHERE token_id=?", (tid,))
    else:
        c.execute("INSERT INTO names(token_id,name,tag,updated) VALUES(?,?,?,?) "
                  "ON CONFLICT(token_id) DO UPDATE SET name=excluded.name,tag=excluded.tag,updated=excluded.updated",
                  (tid, name, tag, time.time()))
    return name, tag, None


def display(name, tag):
    return "[%s] %s" % (tag, name) if tag else name


def state_text(name, tag, err=None):
    """Reply text of 0xD1: ASCII "k=v ..." (spaces in the name -> _)."""
    s = "ok=%d name=%s tag=%s" % (0 if err else 1, (name or "").replace(" ", "_") or "-", tag or "-")
    return s + (" err=%s" % err.replace(" ", "_") if err else "")
