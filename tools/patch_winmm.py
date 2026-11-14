"""Retarget a T2R winmm.dll at a different control server (IP + TCP port).

The client dials the server from two places, each with an XOR-obfuscated IP imm32
and a plain port imm16:
  0x56402 / 0x563F1  session-connect FUN_180056f70
  0x58725 / 0x58742  auth IP/port getters (VMA 0x59321 / 0x59342)
Stored IP = in_addr dword (LE) XOR 0x5a3c9e17. Port = host-order u16 (LE bytes).

Usage: python patch_winmm.py <in.dll> <out.dll> <ip> <port>
  e.g. python patch_winmm.py deploy/winmm.dll local/winmm.dll 127.0.0.1 7001
"""
import socket
import struct
import sys

XOR_KEY = 0x5A3C9E17
IP_OFFS = (0x56402, 0x58725)
PORT_OFFS = (0x563F1, 0x58742)


def current_target(d):
    ips = {socket.inet_ntoa(struct.pack("<I", struct.unpack_from("<I", d, o)[0] ^ XOR_KEY)) for o in IP_OFFS}
    ports = {struct.unpack_from("<H", d, o)[0] for o in PORT_OFFS}
    return ips, ports


def patch(d, ip, port):
    d = bytearray(d)
    ipv = struct.unpack("<I", socket.inet_aton(ip))[0] ^ XOR_KEY
    for o in IP_OFFS:
        struct.pack_into("<I", d, o, ipv)
    for o in PORT_OFFS:
        struct.pack_into("<H", d, o, port)
    return bytes(d)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        print(current_target(open(sys.argv[1], "rb").read()))
        sys.exit(0)
    src, dst, ip, port = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    data = open(src, "rb").read()
    ips, ports = current_target(data)
    if len(ips) != 1 or len(ports) != 1:
        sys.exit(f"unexpected bytes at patch sites: {ips} {ports} (not a T2R winmm.dll?)")
    out = patch(data, ip, port)
    open(dst, "wb").write(out)
    print(f"{src}: {ips.pop()}:{ports.pop()} -> {dst}: {current_target(out)}")
