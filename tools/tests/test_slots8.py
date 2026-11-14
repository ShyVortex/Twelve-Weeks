"""Offline tests for the 8-player winmm (tools/features/slots8*.py): the patched image is loaded into the Unicorn CPU emulator and the
rewritten functions / extended chains are run against synthetic player, peer and anim-slot state (entries 0..3 keep their behaviour,
entries 4..7 must now work).

Run: python tools/tests/test_slots8.py   (plain python; needs `pip install unicorn capstone` and an unpatched winmm.dll: T2R_SLOTS8_BASE,
tools/local/winmm-nocave-127.0.0.1-7001.dll up the tree, or C:/Games/T2R-A/winmm.dll; SKIPs when one is missing; never launches anything)."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "features"))


def find_base():
    c = [os.environ.get("T2R_SLOTS8_BASE", "")]
    d = TOOLS
    for _ in range(8):
        c.append(os.path.join(d, "local", "winmm-nocave-127.0.0.1-7001.dll"))
        c.append(os.path.join(d, "tools", "local", "winmm-nocave-127.0.0.1-7001.dll"))
        d = os.path.dirname(d)
    c.append(r"C:\Games\T2R-A\winmm.dll")
    return next((p for p in c if p and os.path.exists(p)), None)


try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    from unicorn.x86_const import *  # noqa: F401,F403
    import capstone  # noqa: F401
except ImportError as e:
    print("SKIP: " + str(e))
    sys.exit(0)
BASE = find_base()
if not BASE:
    print("SKIP: no unpatched winmm.dll")
    sys.exit(0)
import slots8  # noqa: E402

IMG = 0x180000000
STACK = 0x7ff000000000
RET = 0x7ff100000000
HEAP = 0x7ff200000000
FAILS = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   got %r want %r" % (got, want)))
    if not ok:
        FAILS.append(name)


class Emu:
    def __init__(self, data):
        self.im = slots8.Img(data)
        self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
        for name, va, vsz, rptr, rsz in self.im.secs:
            if name in (b".t2rc", b".rsrc"):
                continue
            sz = (max(vsz, rsz) + 0xfff) & ~0xfff
            self.uc.mem_map(IMG + va, sz)
            if rsz:
                self.uc.mem_write(IMG + va, bytes(data[rptr:rptr + min(rsz, vsz if vsz else rsz)]))
        self.uc.mem_map(STACK - 0x100000, 0x200000)
        self.uc.mem_map(RET, 0x1000)
        self.uc.mem_write(RET, b"\xcc")
        self.uc.mem_map(HEAP, 0x100000)
        self.stubs = {}
        self.calls = []
        self.uc.hook_add(UC_HOOK_CODE, self._code)

    def _code(self, uc, addr, size, ud):
        if addr in self.stubs:
            self.calls.append(addr)
            r = self.stubs[addr](self, uc)
            rsp = uc.reg_read(UC_X86_REG_RSP)
            ret = struct.unpack("<Q", uc.mem_read(rsp, 8))[0]
            uc.reg_write(UC_X86_REG_RAX, r if r is not None else 0)
            uc.reg_write(UC_X86_REG_RSP, rsp + 8)
            uc.reg_write(UC_X86_REG_RIP, ret)

    def stub(self, va, fn):
        self.stubs[va] = fn

    def rd(self, va, n):
        return bytes(self.uc.mem_read(va, n))

    def wr(self, va, b):
        self.uc.mem_write(va, bytes(b))

    def u32(self, va):
        return struct.unpack("<I", self.rd(va, 4))[0]

    def call(self, va, rcx=0, rdx=0, r8=0, r9=0, maxins=200000):
        uc = self.uc
        sp = STACK + 0x80000 - 8
        uc.mem_write(sp, struct.pack("<Q", RET))
        for r, v in ((UC_X86_REG_RCX, rcx), (UC_X86_REG_RDX, rdx), (UC_X86_REG_R8, r8), (UC_X86_REG_R9, r9)):
            uc.reg_write(r, v)
        uc.reg_write(UC_X86_REG_RSP, sp)
        uc.emu_start(va, RET, count=maxins)
        assert uc.reg_read(UC_X86_REG_RSP) == sp + 8, "stack not balanced"
        return uc.reg_read(UC_X86_REG_RAX)

    def run(self, begin, until, regs=None, maxins=20000):
        """run from `begin` (inside a function: the chain tests) until one of the addresses in `until` is reached"""
        uc = self.uc
        uc.reg_write(UC_X86_REG_RSP, STACK + 0x80000 - 0x200)
        uc.reg_write(UC_X86_REG_RBP, STACK + 0x40000)
        for r, v in (regs or {}).items():
            uc.reg_write(r, v)
        reached = []

        def hk(u, addr, size, ud):
            if addr in until:
                reached.append(addr)
                u.emu_stop()
        h = uc.hook_add(UC_HOOK_CODE, hk)
        try:
            uc.emu_start(begin, 0, count=maxins)
        finally:
            uc.hook_del(h)
        return reached[0] if reached else None


def sockaddr(ip, port):
    return struct.pack("<HH", 2, port) + bytes(ip) + b"\0" * 8


def main():
    out, S = slots8.apply(open(BASE, "rb").read())
    e = Emu(out)
    sec = [s for s in e.im.secs if s[0] == b".t2r8"][0]
    base = IMG + sec[1]
    magic, ver, PEERS, PA, PL, SS = struct.unpack("<IIQQQQ", e.rd(base + slots8.CODE_RESERVE, 40))
    check("descriptor", (magic, ver), (slots8.MAGIC, 1))
    L = S.cave.labels
    uc = e.uc
    CTX = 0x180135388
    ST, PAS, RBP = 0x40A0, 0x77E8, STACK + 0x40000

    def rec(j):
        return PL + j * 0xA70

    # ---- net players
    check("netSlot baked in", [e.u32(rec(j)) for j in range(8)], list(range(8)))
    for s, want in ((0, 0), (1, 1), (3, 3), (4, 4), (7, 7), (8, 7), (-1, 0), (1000, 7)):
        check("BySlot(%d)" % s, e.call(0x180050FD0, s & 0xffffffff), rec(want))
    check("Local() none", e.call(0x180051060), 0)
    e.wr(rec(6) + 4, b"\x01\x01")
    check("Local() = record 6", e.call(0x180051060), rec(6))
    e.wr(rec(6) + 4, b"\x00\x00")
    for j in (0, 2, 5, 7):
        e.wr(rec(j) + 4, b"\x01")
    check("ActiveCount", e.call(0x1800512A0), 4)
    e.stub(0x180058A00, lambda em, u: 9)
    e.wr(rec(5) + 0x48, struct.pack("<i", 1))
    e.wr(rec(2) + 0x48, struct.pack("<i", 0))
    e.wr(rec(7) + 0x48, struct.pack("<i", -1))
    check("TeamOf(5)", e.call(0x18004C030, CTX, 5), 1)
    check("TeamOf(2)", e.call(0x18004C030, CTX, 2), 0)
    check("TeamOf(7) falls back to the matchmaker roster", e.call(0x18004C030, CTX, 7), 9)
    check("TeamOf(9) falls back", e.call(0x18004C030, CTX, 9), 9)
    for j in (0, 2, 5, 7):
        e.wr(rec(j), struct.pack("<i", j))
    o = STACK + 0x1000
    e.call(0x1800512F0, o, o + 4)
    check("CountActivePerTeam", struct.unpack("<ii", e.rd(o, 8)), (2, 1))
    e.stub(0x18000A200, lambda em, u: u.reg_read(UC_X86_REG_RCX) ^ 0x1000)
    for j, h in ((5, 0x5000), (7, 0x7000)):
        e.wr(rec(j) + 0x4C, b"\x01")
        e.wr(rec(j) + 0x60, struct.pack("<Q", h))
        check("FromEnginePtr(record %d)" % j, e.call(0x180051120, h ^ 0x1000), rec(j))
    check("FromEnginePtr(null)", e.call(0x180051120, 0), 0)
    check("FromEnginePtr(unknown)", e.call(0x180051120, 0x1234), 0)
    # roster: ApplyRoster / SetupLocal / Reset / iterator over 8 entries
    R = STACK + 0x8000
    payload = bytearray(2 + 8 * 67)
    payload[0], payload[1] = 2, 8
    for i in range(8):
        b = 2 + 67 * i
        payload[b] = i
        payload[b + 1] = 1 if i in (0, 2, 5, 7) else 0
        payload[b + 2] = i & 1
        payload[b + 3:b + 5] = b"P%d" % i
        payload[b + 27:b + 33] = b"look-%d" % i
    for j in range(8):
        e.wr(rec(j) + 4, bytes(2))
    e.wr(R, bytes(payload))
    e.call(0x180051700, R, 2)
    for i in range(8):
        act = (e.rd(rec(i) + 4, 1)[0], e.rd(rec(i) + 5, 1)[0])
        check("ApplyRoster slot %d" % i, act, (1 if i in (0, 2, 5, 7) else 0, 1 if i == 2 else 0))
        if i in (0, 2, 5, 7):
            check("ApplyRoster slot %d name/look/team" % i,
                  (e.rd(rec(i) + 6, 24).split(b"\0")[0], e.rd(rec(i) + 0x1E, 40).split(b"\0")[0], struct.unpack("<i", e.rd(rec(i) + 0x48, 4))[0]),
                  (b"P%d" % i, b"look-%d" % i, i & 1))
    e.wr(R + 0x400, b"Me\0")
    e.wr(R + 0x420, b"mylook\0")
    e.call(0x180051630, 6, R + 0x400, R + 0x420)
    check("SetupLocal(6)", (e.rd(rec(6) + 4, 2), e.rd(rec(6) + 6, 3)), (b"\x01\x01", b"Me\0"))
    e.stub(0x180050C30, lambda em, u: 0)
    e.call(0x180051480)
    check("Reset clears 8 records", [e.rd(rec(i) + 4, 2) for i in range(8)], [b"\0\0"] * 8)
    for i in (1, 3, 5, 6):
        e.wr(rec(i) + 4, b"\x01\x00")
    e.wr(rec(3) + 5, b"\x01")
    it, seq = R + 0x800, []
    e.wr(it, struct.pack("<I", 0))
    for _ in range(10):
        e.call(0x180051410, it)
        v = e.u32(it)
        seq.append(v)
        if v >= 8:
            break
        e.wr(it, struct.pack("<I", v + 1))
    check("RemoteRange visits active remotes, ends at 8", seq, [1, 5, 6, 8])
    # unrolled resets through BySlot
    for j in range(8):
        e.wr(rec(j) + 0xA18, struct.pack("<I", 0x3f800000))
        e.wr(rec(j) + 0x9FC, b"\x01")
        e.wr(rec(j) + 0xA00, struct.pack("<I", 7))
    e.stub(0x1800618E0, lambda em, u: 0)
    e.call(0x180061870)
    check("radar blip reset 0..7", [e.u32(rec(j) + 0xA18) for j in range(8)], [0] * 8)
    e.call(0x18001D080)
    check("grace flags reset 0..7", [(e.rd(rec(j) + 0x9FC, 1)[0], e.u32(rec(j) + 0xA00)) for j in range(8)], [(0, 0)] * 8)

    # ---- peers
    def clear_peers():
        e.wr(PEERS, b"\0" * (8 * ST))

    def peers_with_addrs(target):
        clear_peers()
        for j in range(8):
            e.wr(PEERS + j * ST, b"\x01")
            e.wr(PEERS + j * ST + 4, sockaddr((10, 0, 0, 1 + j), 7000))
        if target is not None:
            e.wr(PEERS + target * ST + 4, FROM)
        e.wr(RBP + 0x40F0, FROM)
    FROM = sockaddr((10, 0, 0, 9), 7000)
    for target in (3, 4, 5, 7, None):
        peers_with_addrs(target)
        r = e.run(0x18005B7C4, {0x18005B7F3, 0x18005C02D})
        if target is None:
            check("Hello PeerForAddr: unknown sender", r, 0x18005C02D)
        else:
            check("Hello PeerForAddr: peer %d" % target, (r, uc.reg_read(UC_X86_REG_RDI)), (0x18005B7F3, PEERS + target * ST))
    for target in (3, 6, None):
        peers_with_addrs(target)
        r = e.run(0x18005BB66, {0x18005BB95, 0x18005B680})
        if target is None:
            check("Goodbye PeerForAddr: unknown sender", r, 0x18005B680)
        else:
            check("Goodbye PeerForAddr: peer %d" % target, (r, uc.reg_read(UC_X86_REG_RCX)), (0x18005BB95, PEERS + target * ST))
    dropped = []
    e.stub(0x18005D900, lambda em, u: dropped.append(u.reg_read(UC_X86_REG_RCX) & 0xffffffff) or 0)
    clear_peers()
    for j in range(8):
        e.wr(PEERS + j * ST, b"\x01")
        e.wr(PEERS + j * ST + 0x14, struct.pack("<f", 100.0))
    for j, t in ((3, 90.0), (5, 94.0), (6, 99.0), (7, 80.0)):
        e.wr(PEERS + j * ST + 0x14, struct.pack("<f", t))
    uc.reg_write(UC_X86_REG_XMM9, struct.unpack("<I", struct.pack("<f", 100.0))[0])
    r = e.run(0x18005CF06, {0x18005CFCE})
    check("Update(): silent peers dropped (3, 5, 7)", (r, dropped), (0x18005CFCE, [3, 5, 7]))
    for act in (None, 4, 7):
        clear_peers()
        if act:
            e.wr(PEERS + act * ST, b"\x01")
        e.run(0x18005D078, {0x18005D08E})
        check("SendPhase: any peer active (%s)" % act, (uc.reg_read(UC_X86_REG_RCX) & 0xff) != 0, act is not None)
    for busy, want in (((1, 2, 3), 4), ((1, 2, 3, 4, 5), 6), ((1, 2, 3, 4, 5, 6, 7), None), ((1,), 2)):
        clear_peers()
        for j in busy:
            e.wr(PEERS + j * ST, b"\x01")
        r = e.run(0x18005C40F, {0x18005C4E2, 0x18005C436, 0x18005C4DC, 0x18005C4CC, 0x18005C4D4})
        slot = {0x18005C4CC: 1, 0x18005C4D4: 2, 0x18005C4DC: 3}.get(r)
        if r == 0x18005C4E2:
            slot = uc.reg_read(UC_X86_REG_R12) & 0xff
        check("Hello: first free slot with peers %s busy" % (busy,), slot if r != 0x18005C436 else None, want)
    HM_ROLE = 0x180177F40
    e.wr(HM_ROLE, b"\x01")
    clear_peers()
    check("IsConnected (host, none)", e.call(0x18005DA70) & 1, 0)
    e.wr(PEERS + 6 * ST, b"\x01")
    check("IsConnected (host, peer 6)", e.call(0x18005DA70) & 1, 1)
    e.wr(HM_ROLE, b"\x00")
    # constructor of the new entries equals a natively constructed g_peers[3]
    e.stub(0x180071718, lambda em, u: (HEAP + 0x1000 + (len(em.calls) * 0x100)) if False else _alloc(em, u))
    st = {"n": HEAP + 0x1000}

    def _alloc(em, u):
        p = st["n"]
        st["n"] += (u.reg_read(UC_X86_REG_RCX) + 15) & ~15
        return p
    e.stub(0x180071718, _alloc)
    clear_peers()
    e.call(L["S8_init_hi_peers"])
    for j in range(4, 8):
        p = PEERS + j * ST
        check("ctor: hi peer %d (slot 0xFF, ready=1, map built)" % j, (e.rd(p, 2), e.u32(p + 0x4098), struct.unpack("<Q", e.rd(p + 0x4060, 8))[0] != 0),
              (b"\x00\xff", 1, True))
    # roster on the wire
    e.stub(0x18007F7B4, lambda em, u: (em.wr(u.reg_read(UC_X86_REG_RCX), b"N" + bytes([0x30 + (u.reg_read(UC_X86_REG_RDX) & 7)])), 0)[1])
    e.stub(0x180058A00, lambda em, u: u.reg_read(UC_X86_REG_RCX) & 1)
    for j in range(8):
        e.wr(rec(j) + 4, bytes(2))
    for j in (0, 3, 6):
        e.wr(rec(j) + 4, b"\x01")
    e.wr(R, b"\xcc" * 600)
    e.call(0x18005E5F0, R, 5)
    rb = e.rd(R, 540)
    check("BuildRoster header (forSlot, count)", (rb[0], rb[1]), (5, 8))
    check("BuildRoster entries", [(rb[2 + 67 * i], rb[3 + 67 * i], rb[4 + 67 * i]) for i in range(8)],
          [(i, 1 if i in (0, 3, 6) else 0, i & 1) for i in range(8)])

    # ---- anim slots (PA_SLOT)
    for full in (0, 1):
        for j in range(8):
            e.wr(PA + j * PAS, b"\xaa" * 16)
            e.wr(PA + j * PAS + 0x2894, b"\x01")
            e.wr(PA + j * PAS + 0x4CB0, struct.pack("<I", 7))
            e.wr(PA + j * PAS + 0x2840, struct.pack("<I", 9))
            e.wr(PA + j * PAS + 0x77E4, struct.pack("<I", 0))
        e.call(0x180029A30, full)
        check("NetAnimClear(%d) base fields, 8 slots" % full, all(e.rd(PA + j * PAS, 16) == b"\0" * 16 and e.rd(PA + j * PAS + 0x2894, 1) == b"\0"
                                                                    and e.u32(PA + j * PAS + 0x4CB0) == 0 for j in range(8)), True)
        check("NetAnimClear(%d) full-only fields" % full, all((e.u32(PA + j * PAS + 0x2840), e.u32(PA + j * PAS + 0x77E4)) == ((0, 2) if full else (9, 0)) for j in range(8)), True)
    for target in (3, 5, 7, None):
        for j in range(8):
            e.wr(PA + j * PAS + 0x2894, b"\x01")
            e.wr(PA + j * PAS, struct.pack("<Q", 0x1000 + j))
        key = 0x1000 + target if target is not None else 0xdead
        r = e.run(0x180026E51, {0x180026E73, 0x180026F8C}, {UC_X86_REG_RCX: key})
        check("anim owner search a: %s" % target, (r, uc.reg_read(UC_X86_REG_RDX) & 0xffffffff) if target else r, (0x180026E73, target) if target else 0x180026F8C)
        r = e.run(0x18002705F, {0x180027075, 0x1800273E1}, {UC_X86_REG_RBX: key})
        check("anim owner search b: %s" % target, (r, uc.reg_read(UC_X86_REG_R15) & 0xffffffff) if target else r, (0x180027075, target) if target else 0x1800273E1)

    # ---- match state: slotState (moved) and stats (grown)
    for j in range(8):
        e.wr(SS + 12 * j + 4, struct.pack("<f", 1.0 + j))
        e.wr(SS + 12 * j + 8, struct.pack("<f", 2.0 + j))
    uc.reg_write(UC_X86_REG_XMM0, 0)
    uc.reg_write(UC_X86_REG_XMM6, struct.unpack("<I", struct.pack("<f", 0.5))[0])
    e.run(0x1800340EB, {0x180034108}, {UC_X86_REG_RAX: CTX})
    check("respawnGrace tick slots 3..7", [struct.unpack("<f", e.rd(SS + 12 * j + 4, 4))[0] for j in range(8)], [1.0, 2.0, 3.0, 3.5, 4.5, 5.5, 6.5, 7.5])
    uc.reg_write(UC_X86_REG_XMM0, 0)
    e.run(0x180034D66, {0x180034D7F}, {UC_X86_REG_RAX: CTX})
    check("grantCooldown tick slots 3..7", [struct.unpack("<f", e.rd(SS + 12 * j + 8, 4))[0] for j in range(8)], [2.0, 3.0, 4.0, 4.5, 5.5, 6.5, 7.5, 8.5])
    e.wr(CTX + 0x2B98, b"\xff" * 96)
    uc.reg_write(UC_X86_REG_XMM0, 0)
    e.run(0x180061F06, {0x180061F1B}, {UC_X86_REG_RAX: CTX})
    check("new match clears stats rows 0..7", e.rd(CTX + 0x2B98, 96), b"\0" * 96)
    print("fails:", len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
