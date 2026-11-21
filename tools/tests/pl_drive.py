"""A/B test aid for private matches with no input driving: send op 0xF8 requests to the daemon AS a game client (its token from
<game folder>/tlou-ii-mp.json), so the lobby / settings pages of the running clients (which poll STATE every 1.2 s while the page is up)
show what the daemon now holds. The pages themselves are pushed with t2r-test-push-once.txt ("to1/private13" / "to1/private13s").

  python tools/tests/pl_drive.py A create                 -> A owns a new lobby (reply printed, code= is the lobby code)
  python tools/tests/pl_drive.py B join ABCDE
  python tools/tests/pl_drive.py A set invuln=1           (any rule key of tools/private_lobby.py RULES, map=<i|-1|-2>, pool=<hex>)
  python tools/tests/pl_drive.py A team 1=0 / kick 1 / start / cancel / leave / state / rules
  python tools/tests/pl_drive.py --selftest               (framing round trip against an in-process fake daemon)

Options: --dir <game folder> (instead of the A / B shorthand), --host 127.0.0.1, --port 7101. The token is never printed.
"""
import json
import os
import socket
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import private_lobby as pl  # noqa: E402

SUBS = {"state": pl.S_STATE, "create": pl.S_CREATE, "join": pl.S_JOIN, "leave": pl.S_LEAVE, "set": pl.S_SET, "team": pl.S_TEAM,
        "kick": pl.S_KICK, "start": pl.S_START, "rules": pl.S_RULES, "cancel": pl.S_CANCEL}
GAME_DIRS = {"A": "C:/Games/T2R-A", "B": "C:/Games/T2R-B"}


def token_of(game_dir):
    with open(os.path.join(game_dir, "tlou-ii-mp.json"), "rb") as f:
        tok = json.loads(f.read().decode("utf-8", "replace")).get("token", "")
    if len(tok) < 64 or any(c not in "0123456789abcdefABCDEF" for c in tok[:64]):
        raise SystemExit(f"no 64-hex token in {game_dir}/tlou-ii-mp.json")
    return tok[:64]


def frame(token, sub, arg=""):
    body = bytes([pl.OP_REQ]) + token.encode("ascii") + bytes([pl.VER, sub]) + arg.encode("ascii")[:47]
    return len(body).to_bytes(2, "little") + body


def ask(token, sub, arg="", host="127.0.0.1", port=7101, timeout=3.0):
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(frame(token, sub, arg))
        buf = b""
        while True:
            if len(buf) >= 2 and len(buf) >= 2 + int.from_bytes(buf[:2], "little"):
                break
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    if len(buf) < 3:
        raise SystemExit("no reply (daemon down, T2R_PRIVATE=0 answers err=off, or a bad token is ignored)")
    n = int.from_bytes(buf[:2], "little")
    if buf[2] != pl.OP_REPLY:
        raise SystemExit(f"unexpected op 0x{buf[2]:02X}")
    return buf[3:2 + n].decode("ascii", "replace")


def selftest():
    lob = pl.Lobbies(nmaps=20)
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]

    def serve():
        for _ in range(4):
            c, _a = srv.accept()
            with c:
                data = c.recv(4096)
                n = int.from_bytes(data[:2], "little")
                assert data[2] == pl.OP_REQ and len(data) == 2 + n
                tok, sub, arg = pl.Lobbies.parse(data[3:2 + n])
                if sub == pl.S_CREATE:
                    lob.create(tok)
                elif sub == pl.S_JOIN:
                    lob.join(tok, arg)
                elif sub == pl.S_SET:
                    lob.set(tok, arg)
                body = bytes([pl.OP_REPLY]) + lob.state_text(tok, lambda t: "P" + t[:2]).encode()
                c.sendall(len(body).to_bytes(2, "little") + body)

    th = threading.Thread(target=serve, daemon=True)
    th.start()
    ta, tb = "a" * 64, "b" * 64
    r = dict(kv.split("=", 1) for kv in ask(ta, pl.S_CREATE, port=port).split())
    assert r["in"] == "1" and r["own"] == "1" and len(r["code"]) == pl.CODE_LEN, r
    r2 = dict(kv.split("=", 1) for kv in ask(tb, pl.S_JOIN, r["code"].lower(), port=port).split())
    assert r2["in"] == "1" and r2["code"] == r["code"] and r2["n"] == "2", r2
    r3 = dict(kv.split("=", 1) for kv in ask(ta, pl.S_SET, "invuln=1", port=port).split())
    assert r3["invuln"] == "1", r3
    r4 = dict(kv.split("=", 1) for kv in ask(tb, pl.S_STATE, port=port).split())
    assert r4["invuln"] == "1" and r4["own"] == "0", r4
    th.join(2)
    print("pl_drive selftest: ok (create / join lower-case code / set / state)")


def main(argv):
    host, port, gdir, rest = "127.0.0.1", 7101, None, []
    it = iter(argv)
    for a in it:
        if a == "--selftest":
            return selftest()
        if a == "--host":
            host = next(it)
        elif a == "--port":
            port = int(next(it))
        elif a == "--dir":
            gdir = next(it)
        else:
            rest.append(a)
    if gdir is None:
        if not rest or rest[0].upper() not in GAME_DIRS:
            raise SystemExit(__doc__)
        gdir = GAME_DIRS[rest.pop(0).upper()]
    if not rest or rest[0] not in SUBS:
        raise SystemExit(__doc__)
    print(ask(token_of(gdir), SUBS[rest[0]], " ".join(rest[1:]), host, port))


if __name__ == "__main__":
    main(sys.argv[1:])
