"""A search refused for want of a Steam helper says "game files changed" when the login token is nameless while a named
helper is connected from the same IP (winmm's substitute token), else the old "Steam is not connected" note.
Run: python tools/tests/test_files_changed_note.py"""
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
daemon.DB_PATH = os.path.join(tmp, "t2r.db"); daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
daemon.evt = lambda *a, **k: None

named = daemon.make_token("Rider")
substitute = "95dacea5" + "ab" * 28
check(daemon.token_name(named) == "Rider" and daemon.token_name(substitute) is None, "fixture tokens: one named, one nameless")
daemon.BRIDGES.register(named, object(), 76561198000000001, port=7777, ip="10.0.0.5", name="Rider")
check(daemon.no_helper_note(substitute, "10.0.0.5") == ("files_changed", "Rider"), "nameless token + named helper on the IP = files changed")
check(daemon.no_helper_note(substitute, "10.0.0.6") == ("steam_off", None), "no helper on the IP = Steam not connected")
check(daemon.no_helper_note(daemon.make_token("Other"), "10.0.0.5") == ("steam_off", None), "a named token is never told its files changed")
daemon.BRIDGES.register(daemon.make_token("Flat"), object(), 76561198000000002, port=7777, ip="10.0.0.5", name="Flatmate")
check(daemon.no_helper_note(substitute, "10.0.0.5") == ("steam_off", None), "two helpers behind one IP = ambiguous, old note")
for lang in ("en", "pl"):
    b = daemon.srv_text("files_changed", lang).encode("utf-8")
    check(len(b) <= 0xf0, "%s note fits the 0x11 frame (%d B)" % (lang, len(b)))
print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
