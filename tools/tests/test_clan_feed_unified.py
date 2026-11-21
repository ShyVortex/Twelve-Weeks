""" the launcher's clan notifications must be the game's. One source of truth: clan_story.menu_lines is a pure function of
(clan key, clan state, time slot, language); the daemon (op 0xB4) and the update server (/clanfeed.json "menu") both serve it.
This test makes a clan the way the game does (token with a Steam id -> key "s:<id>"), then asks BOTH paths at the same instant and requires the same
ids and texts, in English and Polish, across several time slots, with stored events, with a lazily created roster, and for a clan the daemon never touched.
Temp DB only (never port 7001 / tools/t2r.db).   Run: python tools/tests/test_clan_feed_unified.py"""
import os, sqlite3, sys, tempfile, types
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "update_server"))
import daemon, clan, clan_story as CS  # noqa: E402
import clanfeed_view  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

NOW = [1_800_000_000.0]
CS.time = types.SimpleNamespace(time=lambda: NOW[0])      # the clock both paths read (the view also gets it explicitly)

INSTALL = "0123456789abcdef01234567"
TOK = "54324e3a" + "416c696365" + "00" * 11 + INSTALL
SID = 76561198000000042
with daemon.db() as d:
    d.execute("INSERT INTO players(token, name, steamid) VALUES(?,?,?)", (TOK, "Alice", SID))
daemon.clan_side(TOK, 1)                                  # WLF; the clan lives under "s:<steamid>", NOT under the install id
with daemon.db() as d:
    check(daemon.clan_key(d, TOK) == "s:%d" % SID, "the daemon keys the clan by the Steam account")
    check(not d.execute("SELECT 1 FROM clans WHERE token_id=?", (INSTALL,)).fetchone(), "no clan row under the install id")
daemon.clan_match_started([TOK], "mid1")
daemon.clan_report(TOK, 900, 2)

def game(lang):
    return [(str(i), t) for i, t in daemon.feed_latest(TOK, lang=lang)]

def launcher(lang):
    v = clanfeed_view.view(daemon.DB_PATH, INSTALL, lang=lang, now=NOW[0])
    assert v["ok"] and v["hasClan"], v
    return [(m["id"], m["text"]) for m in v["menu"]]

# the view finds the clan under the daemon's key (it used to look under the install id and see no clan at all)
check(clanfeed_view.view(daemon.DB_PATH, INSTALL)["hasClan"], "the launcher view resolves the same clan key as the daemon")
n_checked = 0
for slot in range(8):
    NOW[0] = 1_800_000_000.0 + slot * CS.SLOT_S + 7
    for lang in ("en", "pl"):
        g, l = game(lang), launcher(lang)
        n_checked += 1
        check(g and g == l, "slot %d %s: game == launcher (%d lines, ids + texts)" % (slot, lang, len(g)))
        if g != l:
            print("   game:", g, "\n   view:", l)
# several asks inside one slot give the same answer (no per-request randomness, no per-reader seen-set)
a, b = game("en"), game("en")
NOW[0] += 5
c_ = game("en")
check(a == b == c_ == launcher("en"), "repeated asks in one slot return identical lines")
# and the next slot moves on (new ids, mostly new texts)
NOW[0] += CS.SLOT_S
nxt = game("en")
live = lambda x: {i for i, _ in x if i.startswith("l")}
check(nxt != a and live(nxt) and not (live(nxt) & live(a)), "the next slot brings new live ids")
# the language only changes the text: ids are the same, so a language switch keeps the cycle
check([i for i, _ in game("pl")] == [i for i, _ in game("en")], "Polish and English share the ids")
check(all(x != y for (_, x), (_, y) in zip(game("pl"), game("en"))), "Polish text differs from English")

# a clan with a roster the daemon never created (old clan, numbers only): the read-only view builds the same roster in memory
T2 = "ab" * 20 + "89abcdef0123456789abcdef"[:24]
INSTALL2 = T2[40:]
with daemon.db() as d:
    clan.save(d, INSTALL2, {"faction": clan.SERAPHITES, "status": 1, "day": 6, "healthy": 4, "hungry": 1, "sick": 1})
before = os.path.getmtime(daemon.DB_PATH)
v_first = clanfeed_view.view(daemon.DB_PATH, INSTALL2, now=NOW[0])["menu"]
check(not sqlite3.connect(daemon.DB_PATH).execute("SELECT 1 FROM clan_story WHERE token_id=?", (INSTALL2,)).fetchone(), "the read-only view creates no roster")
g_first = [(str(i), t) for i, t in daemon.feed_latest(T2)]
check(g_first and [(m["id"], m["text"]) for m in v_first] == g_first, "lazy roster: view (in memory) == game (created by the daemon): %s" % (g_first[:1],))
check(sqlite3.connect(daemon.DB_PATH).execute("SELECT 1 FROM clan_story WHERE token_id=?", (INSTALL2,)).fetchone() is not None, "the daemon path created the roster")
check([(m["id"], m["text"]) for m in clanfeed_view.view(daemon.DB_PATH, INSTALL2, now=NOW[0])["menu"]] == g_first, "same lines after the roster exists")

# the launcher uses "menu" when the daemon is unreachable: main.js turns it into the same item list; check the shape it relies on
v = clanfeed_view.view(daemon.DB_PATH, INSTALL, now=NOW[0])
check(isinstance(v["menu"], list) and v["menu"] and all(set(m) == {"id", "text"} and len(m["text"]) <= CS.WIDGET_MAX + 1 for m in v["menu"]) and isinstance(v["slot"], int),
      "view carries menu [{id,text}] + slot")
print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall passed (%d game == launcher comparisons)" % n_checked)
sys.exit(1 if FAILS else 0)
