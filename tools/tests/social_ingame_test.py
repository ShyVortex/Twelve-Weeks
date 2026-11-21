"""social_ingame_test.py - the wire the in-game FRIENDS panel (tools/ext/friends13.c) uses, against a LOCAL daemon (scratch port + scratch database, never the live one):
op 0xD8 framed exactly like friends13.c fr_worker builds it, the 0xD9 JSON read back, the notice poll's flag byte (op 0xBA byte 66: the game has the panel -> request /
invite lines say "Press P"), and friends13.h parsing the daemon's real replies (tools/ext/tests/friends13_test.c, compiled when gcc is found).

  python tools/tests/social_ingame_test.py [--port 17157]
"""
import argparse
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import social  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def name_token(name, id_hex):
    raw = bytearray(32)
    raw[0:4] = b"T2N:"
    nb = name.encode("utf-8")[:15]
    raw[4:4 + len(nb)] = nb
    raw[20:32] = bytes.fromhex(id_hex)
    return raw.hex()


def rpc(port, op, payload, timeout=5):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.sendall(struct.pack("<H", len(payload) + 1) + bytes([op]) + payload)
    data = b""
    while len(data) < 2 or len(data) < 2 + struct.unpack_from("<H", data)[0]:
        b = s.recv(65536)
        if not b:
            break
        data += b
    s.close()
    return data


def d8(port, token, sub, arg="", lang=0):
    """friends13.c fr_worker's frame: 0xD8 [64B token][1][lang][sub][arg utf-8]; returns (reply op, body)."""
    data = rpc(port, 0xD8, token.encode() + bytes([1, lang, sub]) + arg.encode("utf-8"))
    ln = struct.unpack_from("<H", data)[0]
    return data[2], data[3:2 + ln]


def state(port, token, sub=1, arg="", lang=0):
    op, body = d8(port, token, sub, arg, lang)
    assert op == social.OP_REPLY, "reply op %02x" % op
    return json.loads(body.decode("utf-8")), body


def notices(port, token, flag):
    pl = token.encode() + bytes([1, 0] + ([flag] if flag is not None else []))
    data = rpc(port, 0xBA, pl)
    ln = struct.unpack_from("<H", data)[0]
    assert data[2] == 0xBB
    return data[3:2 + ln].decode("utf-8")


def find_gcc():
    g = shutil.which("gcc")
    if g:
        return g
    for c in (os.path.join(os.path.dirname(os.path.dirname(TOOLS)), "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe"),
              "./tools/win/ext/msys64/ucrt64/bin/gcc.exe"):
        if os.path.exists(c):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=17157)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="f2ig-")
    daemon = os.path.join(TOOLS, "daemon.py")
    env = dict(os.environ, T2R_PORT=str(a.port), T2R_DB=os.path.join(tmp, "t2r.db"), T2R_VERSION="test", T2R_HOST="127.0.0.1")
    p = subprocess.Popen([sys.executable, "-I", daemon], cwd=tmp, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                socket.create_connection(("127.0.0.1", a.port), timeout=1).close()
                up = True
                break
            except OSError:
                pass
        check(up, "scratch daemon up on port %d" % a.port)
        if not up:
            return
        A, B, C, D, E = (name_token(n, i * 24) for n, i in (("Anna", "0"), ("Bert", "1"), ("Cleo", "2"), ("Dora", "3"), ("Emil", "4")))
        for t in (A, B, C, D, E):
            r, _ = state(a.port, t)
            check(r["ok"] == 1 and r["me"]["name"], "state of %s over op 0xD8 (%s)" % (r["me"]["name"], r["me"]["id"][:10]))
        # A <-> B friends, A <-> E friends, C asks A, A asks D
        state(a.port, A, social.S_ADD, "Bert")
        r, _ = state(a.port, B)
        state(a.port, B, social.S_ACCEPT, r["in"][0]["id"])
        state(a.port, A, social.S_ADD, "Emil")
        r, _ = state(a.port, E)
        state(a.port, E, social.S_ACCEPT, r["in"][0]["id"])
        state(a.port, C, social.S_ADD, "Anna")
        state(a.port, A, social.S_ADD, "Dora")
        r, _ = state(a.port, E)
        anna_id = next(f["id"] for f in r["friends"] if f["name"] == "Anna")
        r, _ = state(a.port, E, social.S_INVITE, anna_id)
        check(r["ok"] == 1, "Emil invites Anna to a party over the in-game wire: " + r.get("err", ""))
        # notice poll: without the flag the line points at the launcher, with it at P
        t0 = notices(a.port, A, None)
        t1 = notices(a.port, A, 1)
        check("launcher" in t0 and "Press P" not in t0, "notice poll without the flag byte: launcher wording")
        check("|p|" in t1 and "Press P to open FRIENDS" in t1, "notice poll with the flag byte: 'Press P' wording (%s)" % t1.replace("\n", " / ")[:120])
        # state A as the panel sees it
        rA, bodyA = state(a.port, A)
        check(len(rA["friends"]) == 2 and len(rA["in"]) == 1 and len(rA["out"]) == 1 and len(rA["pinv"]) == 1, "Anna: 2 friends, 1 request in, 1 out, 1 party invite")
        open(os.path.join(tmp, "a.json"), "wb").write(bodyA)
        # the party: Anna joins Emil's party; a refused write keeps the state
        emil_id = rA["pinv"][0]["id"]
        r, _ = state(a.port, A, social.S_JOIN, emil_id)
        check(r["ok"] == 1 and r["party"] and len(r["party"]["members"]) == 2 and not r["party"]["meLeader"], "Anna joined Emil's party (member, not leader)")
        r, bodyB = state(a.port, A, social.S_READY, "1")
        check(any(m["me"] and m["ready"] for m in r["party"]["members"]), "ready flag toggles over the wire")
        open(os.path.join(tmp, "b.json"), "wb").write(bodyB)
        r, _ = state(a.port, A, social.S_KICK, emil_id)
        check(r["ok"] == 0 and r["err"] == "notleader" and r["friends"], "a refused write carries the state and the err code")
        r, bodyC = state(a.port, A, social.S_ADD, "nobody-xyz-12")
        check(r["ok"] == 0 and r["err"] == "unknown", "add by an unknown name: err unknown")
        open(os.path.join(tmp, "c.json"), "wb").write(bodyC)
        r, _ = state(a.port, A, social.S_ADD, "Cleo")
        check(r["ok"] == 1 and len(r["friends"]) == 3 and not r["in"], "adding the player who asked first = accepting")
        r, _ = state(a.port, A, social.S_REMOVE, next(f["id"] for f in r["friends"] if f["name"] == "Cleo"))
        check(r["ok"] == 1 and len(r["friends"]) == 2, "remove (also what DECLINE / CANCEL send)")
        r, _ = state(a.port, A, social.S_LEAVE)
        check(r["party"] is None or len(r["party"]["members"]) < 2, "leave")
        # the C parser against the real replies
        gcc = find_gcc()
        if gcc:
            exe = os.path.join(tmp, "friends13_test.exe")
            src = os.path.join(TOOLS, "ext", "tests", "friends13_test.c")
            c = subprocess.run([gcc, "-std=gnu2x", "-O2", "-o", exe, src], capture_output=True, text=True)
            check(c.returncode == 0, "friends13_test.c compiles: " + c.stderr[:200])
            if c.returncode == 0:
                r = subprocess.run([exe] + [os.path.join(tmp, f) for f in ("a.json", "b.json", "c.json")], capture_output=True, text=True, encoding="utf-8")
                print(r.stdout)
                check(r.returncode == 0, "friends13.h parses the daemon's replies (C test)")
        else:
            print("skip  no gcc found: C parser test not run")
    finally:
        p.kill()
        p.wait()
        shutil.rmtree(tmp, ignore_errors=True)
    print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
