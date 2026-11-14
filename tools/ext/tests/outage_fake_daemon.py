"""Fake daemon for the ext outage harness: serves every connection in one chosen misbehaving way.
modes: ok (valid 0xE1 frame) | hang (accept, never answer) | close (accept, read, close) | slow:<ms> (valid frame after a delay)
       | trickle (1 byte / 300 ms, valid frame) | trickle_forever (header says 900, then 1 byte / 300 ms) | garble_len (len says 60000)
       | zerolen (frame len 0, then silence) | short (header says 50, sends 10, closes) | two (valid frame + trailing junk)
       | halfhdr (1 byte then close) | rst (accept, reset) | noread (answers without reading the request)
A closed port (nothing listening) is the 'refused' case; a never-accepted port is made by the test with a listen backlog of 0.
"""
import socket, struct, threading, time


def frame(op, payload):
    return struct.pack("<H", len(payload) + 1) + bytes([op]) + payload


OK = frame(0xE1, b"fac=1 st=1 day=3 h=4 hu=0 s=0 need=2 wk=1 lday=2")


def serve(mode, srv, stop):
    srv.settimeout(0.2)
    while not stop.is_set():
        try:
            c, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        threading.Thread(target=handle, args=(mode, c, stop), daemon=True).start()


def handle(mode, c, stop):
    try:
        c.settimeout(5)
        if mode != "noread":
            try:
                c.recv(256)
            except OSError:
                pass
        if mode in ("ok", "noread"):
            c.sendall(OK)
        elif mode == "hang":
            stop.wait(30)
        elif mode == "close":
            pass
        elif mode.startswith("slow:"):
            time.sleep(int(mode[5:]) / 1000)
            c.sendall(OK)
        elif mode == "trickle":
            for b in OK:
                c.sendall(bytes([b]))
                time.sleep(0.3)
        elif mode == "trickle_forever":
            c.sendall(struct.pack("<H", 900))
            for _ in range(200):
                c.sendall(b"x")
                time.sleep(0.3)
        elif mode == "garble_len":
            c.sendall(struct.pack("<H", 60000) + b"\xE1" + b"y" * 100)
            stop.wait(10)
        elif mode == "zerolen":
            c.sendall(struct.pack("<H", 0) + b"\xE1\xE1\xE1")
            stop.wait(10)
        elif mode == "short":
            c.sendall(struct.pack("<H", 50) + b"\xE1" + b"z" * 8)
        elif mode == "two":
            c.sendall(OK + b"junkjunk")
        elif mode == "halfhdr":
            c.sendall(b"\x05")
        elif mode == "rst":
            c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    except OSError:
        pass
    finally:
        try:
            c.close()
        except OSError:
            pass


def start(mode):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    stop = threading.Event()
    threading.Thread(target=serve, args=(mode, srv, stop), daemon=True).start()
    return srv.getsockname()[1], lambda: (stop.set(), srv.close())
