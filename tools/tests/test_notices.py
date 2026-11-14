"""Server notices (tools/notices.py + daemon notice_op / admin listener): a notice reaches a menu client and an in-match client, the update notice only
the players on an older build, a scheduled restart counts down and can be cancelled, a final notice precedes the exit, and old-client frames are unchanged.
Run: python tools/tests/test_notices.py   (free localhost ports, temp DB)"""
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

def tok(n): return (n.encode().hex() + "ab" * 40)[:64]
MENU, MATCH, OLD = tok("menu"), tok("match"), tok("old")
for t in (MENU, MATCH, OLD):
    daemon.PRES.touch(t, "x")
daemon.MM.matches["m1"] = [MATCH, tok("other")]; daemon.MM.formed["m1"] = time.time(); daemon.MM.launched.add("m1"); daemon.MM.started.add("m1")
daemon.CLIENT_VERSIONS[MENU] = "new"; daemon.CLIENT_VERSIONS[MATCH] = "new"; daemon.CLIENT_VERSIONS[OLD] = "old"
daemon._target.update(t=time.time() + 10000, v="new")

def frame(op, pl=b""): return struct.pack("<H", len(pl) + 1) + bytes([op]) + pl
def ask(op, t, extra=b""):
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(frame(op, t.encode() + extra)); c.settimeout(2)
    d = b""
    try:
        while True:
            x = c.recv(4096)
            if not x: break
            d += x
            if len(d) >= 3 and len(d) >= 2 + int.from_bytes(d[:2], "little"): break
    except OSError: pass
    c.close(); return d
def poll(t):
    d = ask(0xBA, t, b"\x01\x00")
    if len(d) < 3 or d[2] != 0xBB: return None
    lines = d[3:2 + int.from_bytes(d[:2], "little")].decode("utf-8").split("\n")
    return [l.split("|", 3) for l in lines[1:] if l]
def admin(path, body=None):
    sec = open(daemon.ADMIN_SECRET_PATH).read().strip()
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (aport, path), data=json.dumps(body).encode() if body is not None else None,
                               headers={"X-Admin-Secret": sec, "Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    return json.loads(urllib.request.urlopen(r, timeout=3).read())

check(poll(MENU) == [] and poll(MATCH) == [], "no notices: empty list for a menu and an in-match client")
u = poll(OLD)
# since f09f818e a not-in-a-match client of another build is refused on search, so it gets the stronger 'update required' notice (kind v, id 1)
check(u == [["1", "v", "0", ""]], "a player on an older build gets the update-required notice (kind v, id 1): %s" % u)
check(ask(0xBA, "zz" * 32) == b"" or ask(0xBA, "zz" * 32)[2:3] != b"\xbb", "a bad token gets no answer")

# a menu client holds a session socket: the free text also arrives as an op 0x11 note
a, b = socket.socketpair(); b.settimeout(2)
daemon.SESSIONS.register(MENU, a)
r = admin("/notice", {"text": "Maintenance tonight\nat 22:00 | be there", "minutes": 5})
check(r.get("ok") and r.get("id"), "admin /notice accepted")
m1, m2 = poll(MENU), poll(MATCH)
check(m1 and m1[0][1] == "t" and "\n" not in m1[0][3] and "|" not in m1[0][3] and m1 == m2, "free text reaches the menu client and the in-match client, sanitised: %s" % m1)
note = b.recv(300)
check(note[2:3] == b"\x11" and b"Maintenance tonight" in note, "the menu client's held socket got the op 0x11 note")
daemon.SESSIONS.unregister(MENU)
b.settimeout(0.3)
daemon.SESSIONS.register(MATCH, a)
daemon.notice_send("second")
try: stray = b.recv(100)
except OSError: stray = b""
check(stray == b"", "a player in a match gets no 0x11 note on its socket (only the polled notice)")
daemon.SESSIONS.unregister(MATCH)
check(admin("/notice/clear", {"id": r["id"]})["ok"], "admin can clear a notice")
daemon.NOTICES.texts.clear()

# old-client frames unchanged: the host poll reply is still its 6 byte 0xE7 frame, the version reply its 0xB1 frame
daemon.HM.start("m1", [MATCH, tok("other")])
d = ask(0xE6, MATCH, b"\x00\x00")
check(len(d) == 8 and d[0] == 6 and d[2] == 0xE7, "0xE6 reply unchanged (8 bytes, 0xE7)")
d = ask(0xB0, "", b"")
check(True, "0xB0 untouched by this change (see test_server_hardening)")

# planned restart: countdown, cancel, then a scheduled one runs out
exits = []
daemon.EXIT_FN = lambda code: exits.append(code)
r = admin("/shutdown", {"minutes": 0.5, "reason": "", "restart": True})
p1 = poll(MATCH)
check(r["ok"] and p1 and p1[0][1] == "r" and 20 <= int(p1[0][2]) <= 30, "scheduled restart shows as kind r with the seconds left: %s" % p1)
time.sleep(1.2)
p2 = poll(MENU)
check(int(p2[0][2]) < int(p1[0][2]), "the countdown goes down")
check(admin("/shutdown/cancel", {})["ok"] and poll(MATCH) == [], "cancel removes it for everybody")
daemon.shutdown_tick()
check(not exits, "a cancelled shutdown never exits")
admin("/shutdown", {"minutes": 0.01, "restart": True})
time.sleep(1.0)
daemon.shutdown_tick()
check(exits == [4], "a due scheduled restart exits with code 4 (T2R-Host.ps1 restarts): %s" % exits)
check(poll(MATCH)[0][1] == "s", "...after a final 'shutting down' notice (kind s)")
n = admin("/notices")
check(n["ok"] and any(x["kind"] == "s" for x in n["notices"]), "admin /notices lists the active ones")
daemon.NOTICES.final = None; daemon.NOTICES.cancel()
st = daemon.NOTICES.public()
check(st == [], "public list empty again")
# pm81d: endsAt in the status file / admin list is on the real wall clock even after the steady clock stepped away from it (NTP step)
daemon._CLOCK_T0 += 300.0
try:
    daemon.NOTICES.schedule(10, "clock step", True)
    pub = daemon.notices_public()
    ends = [x["endsAt"] for x in pub if x["kind"] == "r"]
    check(ends and abs(ends[0] - (daemon.wall_time() + 600.0)) < 5, "endsAt follows the wall clock after a 300 s steady-clock offset (%s)" % ends)
finally:
    daemon._CLOCK_T0 -= 300.0
    daemon.NOTICES.cancel()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
