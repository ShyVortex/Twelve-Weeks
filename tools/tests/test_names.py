"""Offline tests for custom names + clan tags (tools/names.py + daemon ops 0xD0/0xD2).
Run: python tools/tests/test_names.py   (plain python; temp DB and a free localhost port, never
touches tools/t2r.db or port 7001)."""
import os, sys, socket, struct, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import names  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

ID = "0123456789abcdef01234567"
TOK_A = "54324e3a" + "416c696365" + "00" * 11 + ID            # T2N:Alice + id
TOK_B = "54324e3a" + "426f62" + "00" * 13 + ID                # same install, Steam name changed -> new token
TOK_C = "54324e3a" + "43" + "00" * 15 + "fedcba9876543210fedcba98"
assert len(TOK_A) == len(TOK_B) == len(TOK_C) == 64

# ------------------------------------------------------------------ validation
check(names.clean("Joel", "wlf") == ("Joel", "WLF", None), "tag upper-cased")
check(names.clean("  Ellie   B ", "")[0] == "Ellie B", "spaces trimmed and collapsed")
check(names.clean("A" * 16, "")[2] is not None, "name over 15 chars refused")
check(names.clean("Joel", "ABCDEF")[2] is not None, "tag over 5 chars refused")
check(names.clean("Joel", "A-B")[2] is not None, "tag charset")
check(names.clean("Jo<el", "")[2] is not None, "name charset")
check(names.clean("", "WLF")[2] is not None, "tag without a name refused")
check(names.clean("", "") == ("", "", None), "both empty = clear")
check(names.display("Joel", "WLF") == "[WLF] Joel" and names.display("Joel", "") == "Joel", "display text")
check(len(names.display("A" * 15, "ABCDE")) <= 31, "worst case fits the 31-byte name field")

# ------------------------------------------------------------------ daemon
tmp = tempfile.mkdtemp()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port))
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)

def req(op, payload):
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(struct.pack("<H", len(payload) + 1) + bytes([op]) + payload)
    data = b""
    while len(data) < 2 or len(data) < 2 + struct.unpack_from("<H", data)[0]:
        b = c.recv(4096)
        if not b:
            break
        data += b
    c.close()
    ln = struct.unpack_from("<H", data)[0]
    return data[2], data[3:2 + ln].decode()

def setn(tok, name, tag):
    n, t = name.encode(), tag.encode()
    return req(0xD2, tok.encode() + bytes([len(n)]) + n + bytes([len(t)]) + t)

check(daemon.get_name(TOK_A) == "Alice", "no custom name: setup (T2N) name")
op, txt = req(0xD0, TOK_A.encode())
check(op == 0xD1 and "ok=1" in txt and "name=-" in txt, "0xD0 fresh: " + txt)
op, txt = setn(TOK_A, "Big Joel", "wlf")
check(op == 0xD1 and "ok=1" in txt and "name=Big_Joel" in txt and "tag=WLF" in txt, "0xD2 set: " + txt)
check(daemon.get_name(TOK_A) == "[WLF] Big Joel", "custom name beats the setup name, tag shown")
check(daemon.get_name(TOK_B) == "[WLF] Big Joel", "same install id, other token (Steam rename): same custom name")
check(daemon.get_name(TOK_C) == "C", "another install is untouched")
# precedence over a Steam name stored in the players table
daemon.set_steam(TOK_C, 76561198000000001, "SteamC")
check(daemon.get_name(TOK_C) in ("SteamC", "C"), "steam name path still works (T2N/bridge rules unchanged)")
setn(TOK_C, "Custom C", "")
check(daemon.get_name(TOK_C) == "Custom C", "custom name > Steam name > setup name")
# persistence: reopen DB from scratch
op, txt = req(0xD0, TOK_A.encode())
check("name=Big_Joel" in txt and "tag=WLF" in txt, "read back (persisted in the DB): " + txt)
import sqlite3
rows = sqlite3.connect(daemon.DB_PATH).execute("SELECT token_id,name,tag FROM names ORDER BY token_id").fetchall()
check((ID, "Big Joel", "WLF") in rows, "stored keyed by token id (bytes 20..31)")
# rejects
op, txt = setn(TOK_A, "x" * 16, "")
check("ok=0" in txt and "err=" in txt, "too long refused: " + txt)
op, txt = setn(TOK_A, "Joel", "TOOLONG")
check("ok=0" in txt, "long tag refused: " + txt)
check(daemon.get_name(TOK_A) == "[WLF] Big Joel", "a refused rename changes nothing")
op, txt = req(0xD2, TOK_A.encode() + bytes([200]) + b"ab")
check("ok=0" in txt, "truncated payload refused: " + txt)
# identity keeps stats
daemon.add_matches([TOK_A]); daemon.add_matches([TOK_B])
with daemon._dblock, daemon.db() as c:
    c.execute("UPDATE players SET kills=7, wins=1 WHERE token=?", (TOK_A,))
    c.execute("UPDATE players SET kills=5, wins=2 WHERE token=?", (TOK_B,))
lb = [r for r in daemon.leaderboard(10) if names.token_id(r[0]) == ID]
check(len(lb) == 1 and lb[0][2] == 12 and lb[0][4] == 3 and lb[0][5] == 2 and lb[0][1] == "[WLF] Big Joel",
      "leaderboard: both tokens of one install = one row, stats summed, custom name: " + str(lb))
# the name the lobby / peer table / auth reply use
check(b"[WLF] Big Joel" in daemon.auth_reply(daemon.get_name(TOK_A)), "0x10 auth reply carries the tag + name")
check(b"[WLF] Big Joel" in daemon.build_peer_table([TOK_A]), "peer table (scoreboard) carries it")
# clear
op, txt = setn(TOK_A, "", "")
check("ok=1" in txt and "name=-" in txt and daemon.get_name(TOK_A) == "Alice", "clear -> back to the setup name: " + txt)

print()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
