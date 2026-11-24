"""A launcher token written after a name change (T2N + new name + the same install id) that the game has not linked yet
belongs to the install's Steam account on the FRIENDS page: same friends, no second "t:" account. An install id seen with
two Steam accounts never resolves, and an unknown install stays a "t:" account.
Run: python tools/tests/test_social_rename.py"""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_ADMIN_PORT="0", T2R_STATUS_FILE="0", T2R_P2P="0",
                  T2R_DB=os.path.join(tmp, "t2r.db"))
import daemon  # noqa: E402
import social  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "t2r.db"); daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.evt = lambda *a, **k: None

def launcher_token(name, idhex):
    """= release/launcher/lib/game/identity.js nameToken."""
    raw = bytearray(32)
    raw[0:4] = b"T2N:"
    nb = name.encode("utf-8")[:15]
    raw[4:4 + len(nb)] = nb
    raw[20:32] = bytes.fromhex(idhex)
    return bytes(raw).hex()

COCO, FRIEND, OTHER = 76561198000000101, 76561198000000102, 76561198000000103
ID = "423c6f637c5aca4e98d6c1fd"
old = launcher_token("OldName", ID)
new = launcher_token("NewName", ID)
check(old != new and daemon.names.token_id(old) == daemon.names.token_id(new) == ID, "fixture: rename = new token, same install id")
daemon.set_steam(old, COCO, "OldName")
pal = launcher_token("Pal", "aa" * 12)
daemon.set_steam(pal, FRIEND, "Pal")

S = daemon.SOCIAL
check(S.acct(old) == "s:%d" % COCO, "linked token = Steam account")
check(daemon.token_steamid(new) == 0, "the new token is not linked yet")
check(S.acct(new) == "s:%d" % COCO, "unlinked renamed token = the install's Steam account (was a t: account)")

# friends made before the rename show on the page polled with the new token
check(S.handle(pal, 0, social.S_ADD, "s:%d" % COCO).get("ok") == 1, "pal asks the old account")
r = S.handle(new, 0, social.S_ACCEPT, "s:%d" % FRIEND)
check(r.get("ok") == 1, "accepted from the renamed token")
r = S.handle(new, 0, social.S_STATE)
check([f["id"] for f in r.get("friends", [])] == ["s:%d" % FRIEND], "renamed token's FRIENDS page lists the friend once")
r = S.handle(pal, 0, social.S_STATE)
check([f["id"] for f in r.get("friends", [])] == ["s:%d" % COCO] and not r.get("in"), "pal's list has the player once, no second request")
check(S.handle(new, 0, social.S_ADD, "s:%d" % FRIEND).get("err") == "already", "adding the friend again from the new token = already")

# an install id with two Steam accounts (a shared shipped token) never resolves
SH = "bb" * 12
daemon.set_steam(launcher_token("A", SH), COCO, "A")
daemon.set_steam(launcher_token("B", SH), OTHER, "B")
daemon._tid_sid_cache.clear()
check(S.acct(launcher_token("C", SH)) == social.acct_hash(SH), "shared install id (2 Steam accounts) stays a t: account")

# an install the daemon never linked stays a t: account
check(S.acct(launcher_token("Fresh", "cc" * 12)) == social.acct_hash("cc" * 12), "never-linked install stays a t: account")
print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
