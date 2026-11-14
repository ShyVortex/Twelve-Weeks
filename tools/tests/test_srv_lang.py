"""Server -> player texts are rendered per token in the token's last known language: ops 0xB4 / 0xB6 / 0xBA carry the game's / launcher's language,
the daemon remembers it (client_langs.json), and every refusal / notice / broadcast is rendered per recipient; admin free text may carry a Polish form.
Run: python tools/tests/test_srv_lang.py   (free localhost ports, temp DB)"""
import json, os, socket, struct, sys, tempfile, threading, time, urllib.request
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def freeport():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
port, aport = freeport(), freeport()
TMP = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_DB=os.path.join(TMP, "t2r.db"), T2R_ADMIN_PORT=str(aport), T2R_VERSION="new",
                  T2R_FINAL_WAIT_S="0", T2R_STEAM_ONLY="0")
import daemon  # noqa: E402
import notices  # noqa: E402
threading.Thread(target=daemon.tcp_server, daemon=True).start()
threading.Thread(target=daemon.admin_server, daemon=True).start()
time.sleep(0.5)

def tok(n): return (n.encode().hex() + "cd" * 40)[:64]
EN, PL, OLDEN, OLDPL, NEW = tok("en"), tok("pl"), tok("olden"), tok("oldpl"), tok("stranger")
for t in (EN, PL, OLDEN, OLDPL):
    daemon.PRES.touch(t, "x")
daemon.CLIENT_VERSIONS.update({EN: "new", PL: "new", OLDEN: "old", OLDPL: "old"})
daemon._target.update(t=time.time() + 10000, v="new")

def frame(op, pl=b""): return struct.pack("<H", len(pl) + 1) + bytes([op]) + pl
def ask(op, payload):
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(frame(op, payload)); c.settimeout(2)
    d = b""
    try:
        while True:
            x = c.recv(4096)
            if not x: break
            d += x
            if len(d) >= 3 and len(d) >= 2 + int.from_bytes(d[:2], "little"): break
    except OSError: pass
    c.close(); return d
def poll(t, lang):
    """op 0xBA with an explicit language byte -> [[id, kind, param, text], ..]"""
    d = ask(0xBA, t.encode() + bytes([1, lang]))
    if len(d) < 3 or d[2] != 0xBB: return None
    lines = d[3:2 + int.from_bytes(d[:2], "little")].decode("utf-8").split("\n")
    return [l.split("|", 3) for l in lines[1:] if l]
def admin(path, body=None):
    sec = open(daemon.ADMIN_SECRET_PATH).read().strip()
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (aport, path), data=json.dumps(body).encode() if body is not None else None,
                               headers={"X-Admin-Secret": sec, "Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    return json.loads(urllib.request.urlopen(r, timeout=3).read())
def notes_on(t, fn):
    """what an op 0x11 note push (fn()) puts on the held session socket of token t"""
    a, b = socket.socketpair(); b.settimeout(1)
    daemon.SESSIONS.register(t, a)
    try:
        fn()
        try: d = b.recv(600)
        except OSError: d = b""
    finally:
        daemon.SESSIONS.unregister(t); a.close(); b.close()
    return d[3:2 + int.from_bytes(d[:2], "little")].decode("utf-8") if d[2:3] == b"\x11" else None

# ---- language plumbing
check([daemon.norm_lang(x) for x in (None, b"", 0, b"\x00", 1, b"\x01", "pl", "pl-PL", "en", 7, "xx")] == ["en", "en", "en", "en", "pl", "pl", "pl", "pl", "en", "en", "en"],
      "norm_lang: 1 / pl is Polish, everything else English")
check(daemon.lang_of(EN) == "en" and daemon.lang_of(NEW) == "en", "an unknown token is English")
poll(PL, 1)
check(daemon.lang_of(PL) == "pl" and daemon.lang_of(EN) == "en", "op 0xBA with language 1 records Polish for that token only")
poll(OLDPL, 1); poll(OLDEN, 0)
check(daemon.lang_of(OLDPL) == "pl" and daemon.lang_of(OLDEN) == "en", "second Polish / English token")
daemon.note_lang(NEW, 1)
check(NEW not in daemon.CLIENT_LANGS, "an identity the server has never seen is not recorded (no table growth from random tokens)")
daemon.note_lang("zz" * 32, 1); daemon.note_lang(None, 1)
check("zz" * 32 not in daemon.CLIENT_LANGS, "a malformed token is ignored")
poll(PL, 0)
check(daemon.lang_of(PL) == "en", "the last language wins (back to English)")
poll(PL, 1)
daemon.note_lang(EN, 1); daemon.note_lang(EN, 0)
check(daemon.lang_of(EN) == "en" and EN not in daemon.CLIENT_LANGS, "English tokens keep no entry")
feed = ask(0xB4, EN.encode() + b"\x01")
check(daemon.lang_of(EN) == "pl", "op 0xB4 (clan feed) records the game's language too")
ask(0xB4, EN.encode() + b"\x00")
check(daemon.lang_of(EN) == "en", "...and takes it back")
clan = ask(0xB6, EN.encode() + b"\x01\x04")
check(daemon.lang_of(EN) == "pl", "op 0xB6 (in-game clan page) records it")
ask(0xB6, EN.encode() + b"\x00\x04")
check(daemon.lang_of(EN) == "en", "...and takes it back")

# persistence next to client_versions.json
daemon._save_client_langs()
saved = json.load(open(daemon.LANGS_PATH, encoding="utf-8"))
check(saved.get(PL) == "pl" and saved.get(OLDPL) == "pl" and EN not in saved and OLDEN not in saved, "client_langs.json holds the Polish tokens: %s" % sorted(k[:6] for k in saved))
check(os.path.dirname(daemon.LANGS_PATH) == os.path.dirname(daemon.VERSIONS_PATH), "it lives next to client_versions.json")
daemon.CLIENT_LANGS.clear()
with open(daemon.LANGS_PATH, "r", encoding="utf-8") as f:
    daemon.CLIENT_LANGS.update({k: "pl" for k, v in json.load(f).items() if v == "pl"})
check(daemon.lang_of(PL) == "pl", "reloaded table keeps the language across a restart")

# ---- string table
check(daemon.srv_text("banned", "pl") != daemon.srv_text("banned", "en") and daemon.srv_text("banned") == "You are banned from the server.", "srv_text: English default, Polish on request")
bad = [k for k, (en, pl) in daemon.SRV_TEXT.items() if not en or not pl or en == pl or " / " in en or " / " in pl]
check(not bad, "every string has an English and a Polish form, none of them bilingual: %s" % bad)
import re
check(all(sorted(re.findall(r"\{(\w+)\}", en)) == sorted(re.findall(r"\{(\w+)\}", pl)) for en, pl in daemon.SRV_TEXT.values()), "both forms of a string use the same placeholders")
check("Dostępna" in daemon.srv_text("update_refusal", "pl") and "available" in daemon.srv_text("update_refusal", "en"), "the update refusal is ONE language per player")
check("Dostepna" not in daemon.UPDATE_REFUSAL_NOTE and "/" not in daemon.UPDATE_REFUSAL_NOTE, "UPDATE_REFUSAL_NOTE is no longer 'English / Polish'")

# ---- version refusal / mismatch per token
daemon.REQUIRE_VERSION = True
check("restart the launcher" in daemon.version_refusal(OLDEN), "refusal for an English token is English: %s" % daemon.version_refusal(OLDEN))
check("uruchom ponownie launcher" in daemon.version_refusal(OLDPL) and "restart" not in daemon.version_refusal(OLDPL), "refusal for a Polish token is Polish only: %s" % daemon.version_refusal(OLDPL))
check(daemon.version_refusal(EN) is None, "a current build is not refused")
check(daemon.version_problem(OLDPL).startswith("Niezgodność wersji: twoja gra to kompilacja old, a serwer działa na new"), "version mismatch text, Polish")
check(daemon.version_problem(OLDEN).startswith("Version mismatch: your game is build old but this server runs new"), "version mismatch text, English")
daemon.LINUX_CLIENTS.add(OLDPL)
check("Linuksa" in daemon.version_problem(OLDPL), "the Linux form is localized as well")
daemon.LINUX_CLIENTS.discard(OLDPL)
daemon.CLIENT_VERSIONS.pop(NEW, None)
daemon.CLIENT_LANGS[NEW] = "pl"
check("nie zgłosiła" in daemon.version_problem(NEW), "'did not report its version' in Polish")
daemon.CLIENT_LANGS.pop(NEW, None)
check("did not report" in daemon.version_problem(NEW), "...and English")
daemon.REQUIRE_VERSION = False
r = daemon.version_op(bytes([3]) + b"old" + OLDPL.encode())
check(b"Niezg" in r and b"Version mismatch" not in r, "op 0xB0 reply msg= follows the token's language")
r = daemon.version_op(bytes([3]) + b"old" + OLDEN.encode())
check(b"Version mismatch" in r, "op 0xB0 reply for an English token")
check(b"Nieprawid" not in daemon.version_op(b""), "malformed op 0xB0 request stays English (no token)")

# ---- notice kinds and free text per recipient
check(poll(OLDPL, 1) == [["1", "v", "0", ""]], "kind v is language-neutral on the wire (the game renders its own text)")
check("Server restarting in 3 min" in daemon.notice_text("r", 150, "", "en") and "Restart serwera za 3 min" in daemon.notice_text("r", 150, "", "pl"), "notice_text r")
check(daemon.notice_text("r", 60, "patch", "pl") == "Restart serwera za 1 min - patch" and daemon.notice_text("t", 8, "as typed", "pl") == "as typed", "notice_text r with reason / t passes through")
check(daemon.notice_english("s", 0, "") == daemon.srv_text("shutdown", "en"), "notice_english kept for old callers")

r = admin("/notice", {"text": "Server updating", "text_pl": "Serwer się aktualizuje", "seconds": 10})
check(r.get("ok"), "admin /notice with an English and a Polish text")
pe, pp = poll(EN, 0), poll(PL, 1)
check(pe[0][1] == "t" and pe[0][3] == "Server updating", "an English player gets the English text only: %s" % pe)
check(pp[0][1] == "t" and pp[0][3] == "Serwer się aktualizuje", "a Polish player gets the Polish text only: %s" % pp)
check(poll(PL, 0)[0][3] == "Server updating", "the poll's own language byte wins right away (launcher / game switched language)")
pub = admin("/notices")["notices"]
check(pub and pub[0]["text"] == "Server updating" and pub[0]["text_pl"] == "Serwer się aktualizuje", "the public list (status.json / launcher fallback) carries both forms")
admin("/notice/clear", {"id": r["id"]})
daemon.NOTICES.texts.clear()
r = admin("/notice", {"text": "Only English typed", "seconds": 10})
check(poll(PL, 1)[0][3] == "Only English typed" and "text_pl" not in admin("/notices")["notices"][0], "no Polish form typed: everybody gets the text as typed")
daemon.NOTICES.texts.clear()
r = admin("/notice", {"text": "", "text_pl": "Tylko po polsku", "seconds": 10})
check(r.get("ok") and poll(EN, 0)[0][3] == "Tylko po polsku" and poll(PL, 1)[0][3] == "Tylko po polsku", "only a Polish text typed: sent as typed to all")
daemon.NOTICES.texts.clear()
check(not admin("/notice", {"text": "", "text_pl": ""}).get("ok"), "empty notice refused")

# broadcast as op 0x11 note: rendered per recipient
daemon.NOTICES.texts.clear()
check(notes_on(EN, lambda: daemon.notice_send("Maintenance", 5, 8, "Konserwacja")) == "Maintenance", "menu note, English player")
check(notes_on(PL, lambda: daemon.notice_send("Maintenance", 5, 8, "Konserwacja")) == "Konserwacja", "menu note, Polish player")
daemon.NOTICES.texts.clear()
a1, b1 = socket.socketpair(); a2, b2 = socket.socketpair(); b1.settimeout(1); b2.settimeout(1)
daemon.SESSIONS.register(EN, a1); daemon.SESSIONS.register(PL, a2)
daemon.shutdown_schedule(10, "patch", True, "łatka")
g1, g2 = b1.recv(400), b2.recv(400)
check(g1[3:].decode() == "Server restarting in 10 min - patch" and g2[3:].decode() == "Restart serwera za 10 min - łatka",
      "one broadcast, two recipients, two languages: %r / %r" % (g1[3:], g2[3:]))
pr = poll(PL, 1); pe = poll(EN, 0)
check(pr[0][1] == "r" and pr[0][3] == "łatka" and pe[0][3] == "patch", "scheduled-restart reason per language in the notice poll")
daemon.shutdown_cancel()
g1, g2 = b1.recv(400), b2.recv(400)
check(g1[3:].decode() == "Planned server restart cancelled." and g2[3:].decode() == "Planowany restart serwera został odwołany.", "cancel note per language")
daemon.shutdown_schedule(10, "")
b1.recv(400); b2.recv(400)
daemon.shutdown_cancel(); b1.recv(400); b2.recv(400)
daemon.EXIT_FN = lambda code: None
daemon.final_exit("test")
g1, g2 = b1.recv(400), b2.recv(400)
check(g1[3:].decode().startswith("Server is shutting down") and g2[3:].decode().startswith("Serwer się wyłącza"), "final 'shutting down' note per language")
daemon.SESSIONS.unregister(EN); daemon.SESSIONS.unregister(PL)

# ---- the remaining pushes
check(daemon.kick_text("griefing", "pl") == 'Wyrzucono cię z meczu. Powód: "griefing"' and daemon.kick_text("", "pl") == "Wyrzucono cię z meczu."
      and daemon.kick_text("x") == 'You got kicked from the match. Reason: "x"', "kick text per language (reason as typed)")
check(daemon.ban_note(PL).decode("utf-8") == "Masz zakaz wstępu na serwer." and daemon.ban_note(EN) == b"You are banned from the server." and daemon.ban_note(None) == daemon.BAN_MSG, "ban note per token")
check(daemon.srv_note("dropped", PL).decode("utf-8").startswith("Jeden z graczy") and daemon.srv_note("dropped", EN) == b"A player dropped out - searching again", "match-flow notes per token")
check(daemon.srv_note("warn", PL, t="graj fair").decode("utf-8") == "Ostrzeżenie od zespołu Twelve Weeks: graj fair", "anti-cheat warning wrapper per token, admin text as typed")
check(len(daemon.srv_note("warn", PL, t="x" * 500)) <= 0xf0, "notes stay under the 0xf0 byte cap")
check(daemon.srv_text("load_named", "pl", n="A{b}") == "A{b} nie mógł wczytać mapy - mecz został odwołany", "names with braces are never re-parsed")

print("all passed" if not FAILS else "FAILED: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
