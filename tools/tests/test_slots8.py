"""Offline tests for the N-player winmm (tools/features/slots8*.py, N = 8 and 9): the patched image is loaded into the Unicorn CPU emulator and the
rewritten functions / extended chains are run against synthetic player, peer and anim-slot state (entries 0..3 keep their behaviour,
entries 4..N-1 must now work).

Run: python tools/tests/test_slots8.py [N ...]   (default: 8 and 9; plain python; needs `pip install unicorn capstone` and a base winmm.dll: T2R_SLOTS8_BASE,
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
    try:                                    # a git checkout without tools/local: the main checkout's copy (git-common-dir = <main>/.git)
        import subprocess
        gd = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=TOOLS, capture_output=True, text=True).stdout.strip()
        c.append(os.path.join(os.path.dirname(os.path.abspath(os.path.join(TOOLS, gd))), "tools", "local", "winmm-nocave-127.0.0.1-7001.dll"))
    except Exception:
        pass
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
    print("SKIP: no base winmm.dll")
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


def main(N=8):
    print("=== N = %d ===" % N)
    out, S = slots8.apply(open(BASE, "rb").read(), N)
    e = Emu(out)
    sec = [s for s in e.im.secs if s[0] == b".t2r8"][0]
    base = IMG + sec[1]
    magic, ver, PEERS, PA, PL, SS = struct.unpack("<IIQQQQ", e.rd(base + slots8.CODE_RESERVE, 40))
    check("descriptor", (magic, ver), (slots8.MAGIC, 1 if N == 8 else 2))
    STATS = 0
    if N != 8:
        dn, dproto, STATS = struct.unpack("<IIQ", e.rd(base + slots8.CODE_RESERVE + 40, 16))
        check("descriptor N / protocol version / stats table", (dn, dproto, STATS != 0), (N, 0x2A + N - 8, N * 12 > 96))
    L = S.cave.labels
    uc = e.uc
    CTX = 0x180135388
    ST, PAS, RBP = 0x40A0, 0x77E8, STACK + 0x40000
    LAST = N - 1
    ACT = (0, 2, 5, LAST)                       # active records / peers used below

    def rec(j):
        return PL + j * 0xA70

    # ---- net players
    check("netSlot baked in", [e.u32(rec(j)) for j in range(N)], list(range(N)))
    for s, want in ((0, 0), (1, 1), (3, 3), (4, 4), (LAST, LAST), (N, LAST), (-1, 0), (1000, LAST)):
        check("BySlot(%d)" % s, e.call(0x180050FD0, s & 0xffffffff), rec(want))
    check("Local() none", e.call(0x180051060), 0)
    e.wr(rec(LAST - 1) + 4, b"\x01\x01")
    check("Local() = record %d" % (LAST - 1), e.call(0x180051060), rec(LAST - 1))
    e.wr(rec(LAST - 1) + 4, b"\x00\x00")
    for j in ACT:
        e.wr(rec(j) + 4, b"\x01")
    check("ActiveCount", e.call(0x1800512A0), 4)
    e.stub(0x180058A00, lambda em, u: 9)
    e.wr(rec(5) + 0x48, struct.pack("<i", 1))
    e.wr(rec(2) + 0x48, struct.pack("<i", 0))
    e.wr(rec(LAST) + 0x48, struct.pack("<i", -1))
    check("TeamOf(5)", e.call(0x18004C030, CTX, 5), 1)
    check("TeamOf(2)", e.call(0x18004C030, CTX, 2), 0)
    check("TeamOf(%d) falls back to the matchmaker roster" % LAST, e.call(0x18004C030, CTX, LAST), 9)
    check("TeamOf(%d) falls back" % (N + 1), e.call(0x18004C030, CTX, N + 1), 9)
    for j in ACT:
        e.wr(rec(j), struct.pack("<i", j))
    o = STACK + 0x1000
    e.call(0x1800512F0, o, o + 4)
    check("CountActivePerTeam", struct.unpack("<ii", e.rd(o, 8)), (2, 1))
    e.stub(0x18000A200, lambda em, u: u.reg_read(UC_X86_REG_RCX) ^ 0x1000)
    for j, h in ((5, 0x5000), (LAST, 0x7000)):
        e.wr(rec(j) + 0x4C, b"\x01")
        e.wr(rec(j) + 0x60, struct.pack("<Q", h))
        check("FromEnginePtr(record %d)" % j, e.call(0x180051120, h ^ 0x1000), rec(j))
    check("FromEnginePtr(null)", e.call(0x180051120, 0), 0)
    check("FromEnginePtr(unknown)", e.call(0x180051120, 0x1234), 0)
    # roster: ApplyRoster / SetupLocal / Reset / iterator over N entries
    R = STACK + 0x8000
    payload = bytearray(2 + N * 67)
    payload[0], payload[1] = 2, N
    for i in range(N):
        b = 2 + 67 * i
        payload[b] = i
        payload[b + 1] = 1 if i in ACT else 0
        payload[b + 2] = i & 1
        payload[b + 3:b + 5] = b"P%d" % i
        payload[b + 27:b + 33] = b"look-%d" % i
    for j in range(N):
        e.wr(rec(j) + 4, bytes(2))
    e.wr(R, bytes(payload))
    e.call(0x180051700, R, 2)
    for i in range(N):
        act = (e.rd(rec(i) + 4, 1)[0], e.rd(rec(i) + 5, 1)[0])
        check("ApplyRoster slot %d" % i, act, (1 if i in ACT else 0, 1 if i == 2 else 0))
        if i in ACT:
            check("ApplyRoster slot %d name/look/team" % i,
                  (e.rd(rec(i) + 6, 24).split(b"\0")[0], e.rd(rec(i) + 0x1E, 40).split(b"\0")[0], struct.unpack("<i", e.rd(rec(i) + 0x48, 4))[0]),
                  (b"P%d" % i, b"look-%d" % i, i & 1))
    e.wr(R + 0x400, b"Me\0")
    e.wr(R + 0x420, b"mylook\0")
    e.call(0x180051630, LAST - 1, R + 0x400, R + 0x420)
    check("SetupLocal(%d)" % (LAST - 1), (e.rd(rec(LAST - 1) + 4, 2), e.rd(rec(LAST - 1) + 6, 3)), (b"\x01\x01", b"Me\0"))
    e.call(0x180051630, N + 5, R + 0x400, R + 0x420)
    check("SetupLocal clamps to record %d" % LAST, (e.rd(rec(LAST) + 4, 2), e.rd(rec(LAST) + 6, 3)), (b"\x01\x01", b"Me\0"))
    e.stub(0x180050C30, lambda em, u: 0)
    e.call(0x180051480)
    check("Reset clears %d records" % N, [e.rd(rec(i) + 4, 2) for i in range(N)], [b"\0\0"] * N)
    for i in (1, 3, 5, 6):
        e.wr(rec(i) + 4, b"\x01\x00")
    e.wr(rec(3) + 5, b"\x01")
    it, seq = R + 0x800, []
    e.wr(it, struct.pack("<I", 0))
    for _ in range(N + 2):
        e.call(0x180051410, it)
        v = e.u32(it)
        seq.append(v)
        if v >= N:
            break
        e.wr(it, struct.pack("<I", v + 1))
    check("RemoteRange visits active remotes, ends at %d" % N, seq, [1, 5, 6, N])
    # the last record is visited as well
    e.wr(rec(LAST) + 4, b"\x01\x00")
    e.wr(it, struct.pack("<I", 7))
    seq = []
    for _ in range(N + 2):
        e.call(0x180051410, it)
        v = e.u32(it)
        seq.append(v)
        if v >= N:
            break
        e.wr(it, struct.pack("<I", v + 1))
    check("RemoteRange reaches the last record (%d)" % LAST, seq, [LAST, N])
    # unrolled resets through BySlot
    for j in range(N):
        e.wr(rec(j) + 0xA18, struct.pack("<I", 0x3f800000))
        e.wr(rec(j) + 0x9FC, b"\x01")
        e.wr(rec(j) + 0xA00, struct.pack("<I", 7))
    e.stub(0x1800618E0, lambda em, u: 0)
    e.call(0x180061870)
    check("radar blip reset 0..%d" % LAST, [e.u32(rec(j) + 0xA18) for j in range(N)], [0] * N)
    e.call(0x18001D080)
    check("grace flags reset 0..%d" % LAST, [(e.rd(rec(j) + 0x9FC, 1)[0], e.u32(rec(j) + 0xA00)) for j in range(N)], [(0, 0)] * N)

    # ---- peers
    def clear_peers():
        e.wr(PEERS, b"\0" * (N * ST))

    def peers_with_addrs(target):
        clear_peers()
        for j in range(N):
            e.wr(PEERS + j * ST, b"\x01")
            e.wr(PEERS + j * ST + 4, sockaddr((10, 0, 0, 1 + j), 7000))
        if target is not None:
            e.wr(PEERS + target * ST + 4, FROM)
        e.wr(RBP + 0x40F0, FROM)
    FROM = sockaddr((10, 0, 0, 99), 7000)
    for target in (3, 4, 5, LAST, None):
        peers_with_addrs(target)
        r = e.run(0x18005B7C4, {0x18005B7F3, 0x18005C02D})
        if target is None:
            check("Hello PeerForAddr: unknown sender", r, 0x18005C02D)
        else:
            check("Hello PeerForAddr: peer %d" % target, (r, uc.reg_read(UC_X86_REG_RDI)), (0x18005B7F3, PEERS + target * ST))
    for target in (3, 6, LAST, None):
        peers_with_addrs(target)
        r = e.run(0x18005BB66, {0x18005BB95, 0x18005B680})
        if target is None:
            check("Goodbye PeerForAddr: unknown sender", r, 0x18005B680)
        else:
            check("Goodbye PeerForAddr: peer %d" % target, (r, uc.reg_read(UC_X86_REG_RCX)), (0x18005BB95, PEERS + target * ST))
    dropped = []
    e.stub(0x18005D900, lambda em, u: dropped.append(u.reg_read(UC_X86_REG_RCX) & 0xffffffff) or 0)
    clear_peers()
    for j in range(N):
        e.wr(PEERS + j * ST, b"\x01")
        e.wr(PEERS + j * ST + 0x14, struct.pack("<f", 100.0))
    for j, t in ((3, 90.0), (5, 94.0), (6, 99.0), (LAST, 80.0)):
        e.wr(PEERS + j * ST + 0x14, struct.pack("<f", t))
    uc.reg_write(UC_X86_REG_XMM9, struct.unpack("<I", struct.pack("<f", 100.0))[0])
    r = e.run(0x18005CF06, {0x18005CFCE})
    check("Update(): silent peers dropped (3, 5, %d)" % LAST, (r, dropped), (0x18005CFCE, [3, 5, LAST]))
    for act in (None, 4, LAST):
        clear_peers()
        if act:
            e.wr(PEERS + act * ST, b"\x01")
        e.run(0x18005D078, {0x18005D08E})
        check("SendPhase: any peer active (%s)" % act, (uc.reg_read(UC_X86_REG_RCX) & 0xff) != 0, act is not None)
    for busy, want in (((1, 2, 3), 4), ((1, 2, 3, 4, 5), 6), (tuple(range(1, N - 1)), LAST), (tuple(range(1, N)), None), ((1,), 2)):
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
    for pj in (6, LAST):
        clear_peers()
        e.wr(PEERS + pj * ST, b"\x01")
        check("IsConnected (host, peer %d)" % pj, e.call(0x18005DA70) & 1, 1)
    e.wr(HM_ROLE, b"\x00")
    # constructor of the new entries equals a natively constructed g_peers[3]
    st = {"n": HEAP + 0x1000}

    def _alloc(em, u):
        p = st["n"]
        st["n"] += (u.reg_read(UC_X86_REG_RCX) + 15) & ~15
        return p
    e.stub(0x180071718, _alloc)
    clear_peers()
    e.call(L["S8_init_hi_peers"])
    for j in range(4, N):
        p = PEERS + j * ST
        check("ctor: hi peer %d (slot 0xFF, ready=1, map built)" % j, (e.rd(p, 2), e.u32(p + 0x4098), struct.unpack("<Q", e.rd(p + 0x4060, 8))[0] != 0),
              (b"\x00\xff", 1, True))
    # roster on the wire
    e.stub(0x18007F7B4, lambda em, u: (em.wr(u.reg_read(UC_X86_REG_RCX), b"N" + bytes([0x30 + (u.reg_read(UC_X86_REG_RDX) & 7)])), 0)[1])
    e.stub(0x180058A00, lambda em, u: u.reg_read(UC_X86_REG_RCX) & 1)
    for j in range(N):
        e.wr(rec(j) + 4, bytes(2))
    for j in (0, 3, 6, LAST):
        e.wr(rec(j) + 4, b"\x01")
    RN = 2 + 67 * N
    e.wr(R, b"\xcc" * (RN + 64))
    e.call(0x18005E5F0, R, 5)
    rb = e.rd(R, RN + 2)
    check("BuildRoster header (forSlot, count)", (rb[0], rb[1]), (5, N))
    check("BuildRoster entries", [(rb[2 + 67 * i], rb[3 + 67 * i], rb[4 + 67 * i]) for i in range(N)],
          [(i, 1 if i in (0, 3, 6, LAST) else 0, i & 1) for i in range(N)])
    check("BuildRoster writes exactly %d bytes (0x%X)" % (RN, RN), rb[RN:RN + 2], b"\xcc\xcc")
    # BroadcastRoster (host): every active peer gets BuildRoster's buffer (2 + 67 N bytes) through SendRaw (FUN_18005A9F0): its stack
    # frame has to hold the buffer (0x40 + RN bytes above rsp)
    HM_ROLE = 0x180177F40
    sent = []

    def _send(em, u):
        rsp = u.reg_read(UC_X86_REG_RSP)
        ln = struct.unpack("<Q", em.rd(rsp + 8 + 0x28, 8))[0]
        bufp = struct.unpack("<Q", em.rd(rsp + 8 + 0x20, 8))[0]
        sent.append((u.reg_read(UC_X86_REG_RCX), u.reg_read(UC_X86_REG_RDX) & 0xff, ln, bufp, rsp, em.rd(bufp, 2)[1]))
        return 0
    e.stub(0x18005A9F0, _send)
    e.wr(HM_ROLE, b"\x01")
    clear_peers()
    for j in (1, 4, LAST):
        e.wr(PEERS + j * ST, b"\x01")
        e.wr(PEERS + j * ST + 1, bytes([j]))
    e.call(0x18005DB30)
    check("BroadcastRoster: one send per active peer, length %d" % RN, [(s[0], s[1], s[2], s[5]) for s in sent],
          [(PEERS + j * ST, 4, RN, N) for j in (1, 4, LAST)])
    check("BroadcastRoster: buffer inside the frame (0x40 + %d <= frame)" % RN, all(s[3] + RN <= s[4] + 8 + max(0x270, (0x40 + RN + 15) & ~15) for s in sent), True)
    e.wr(HM_ROLE, b"\x00")

    # ---- anim slots (PA_SLOT)
    for full in (0, 1):
        for j in range(N):
            e.wr(PA + j * PAS, b"\xaa" * 16)
            e.wr(PA + j * PAS + 0x2894, b"\x01")
            e.wr(PA + j * PAS + 0x4CB0, struct.pack("<I", 7))
            e.wr(PA + j * PAS + 0x2840, struct.pack("<I", 9))
            e.wr(PA + j * PAS + 0x77E4, struct.pack("<I", 0))
        e.call(0x180029A30, full)
        check("NetAnimClear(%d) base fields, %d slots" % (full, N), all(e.rd(PA + j * PAS, 16) == b"\0" * 16 and e.rd(PA + j * PAS + 0x2894, 1) == b"\0"
                                                                    and e.u32(PA + j * PAS + 0x4CB0) == 0 for j in range(N)), True)
        check("NetAnimClear(%d) full-only fields" % full, all((e.u32(PA + j * PAS + 0x2840), e.u32(PA + j * PAS + 0x77E4)) == ((0, 2) if full else (9, 0)) for j in range(N)), True)
    for target in (3, 5, LAST, None):
        for j in range(N):
            e.wr(PA + j * PAS + 0x2894, b"\x01")
            e.wr(PA + j * PAS, struct.pack("<Q", 0x1000 + j))
        key = 0x1000 + target if target is not None else 0xdead
        r = e.run(0x180026E51, {0x180026E73, 0x180026F8C}, {UC_X86_REG_RCX: key})
        check("anim owner search a: %s" % target, (r, uc.reg_read(UC_X86_REG_RDX) & 0xffffffff) if target else r, (0x180026E73, target) if target else 0x180026F8C)
        r = e.run(0x18002705F, {0x180027075, 0x1800273E1}, {UC_X86_REG_RBX: key})
        check("anim owner search b: %s" % target, (r, uc.reg_read(UC_X86_REG_R15) & 0xffffffff) if target else r, (0x180027075, target) if target else 0x1800273E1)
    # the anim offset loop (FUN_180028C40 ends at N * 0x77E8)
    ins = [i for i in slots8._MD.disasm(e.rd(0x180028CE7, 7), 0x180028CE7)]
    check("anim offset loop end", ins[0].operands[-1].imm, N * PAS)

    # ---- match state: slotState (moved) and stats (grown / moved)
    for j in range(N):
        e.wr(SS + 12 * j + 4, struct.pack("<f", 1.0 + j))
        e.wr(SS + 12 * j + 8, struct.pack("<f", 2.0 + j))
    uc.reg_write(UC_X86_REG_XMM0, 0)
    uc.reg_write(UC_X86_REG_XMM6, struct.unpack("<I", struct.pack("<f", 0.5))[0])
    e.run(0x1800340EB, {0x180034108}, {UC_X86_REG_RAX: CTX})
    check("respawnGrace tick slots 3..%d" % LAST, [struct.unpack("<f", e.rd(SS + 12 * j + 4, 4))[0] for j in range(N)],
          [1.0 + j - (0.5 if j >= 3 else 0.0) for j in range(N)])
    uc.reg_write(UC_X86_REG_XMM0, 0)
    e.run(0x180034D66, {0x180034D7F}, {UC_X86_REG_RAX: CTX})
    check("grantCooldown tick slots 3..%d" % LAST, [struct.unpack("<f", e.rd(SS + 12 * j + 8, 4))[0] for j in range(N)],
          [2.0 + j - (0.5 if j >= 3 else 0.0) for j in range(N)])
    # ResetRuntime tail: slotState 4..N-1 zeroed, the displaced store after it, and nothing outside the table touched
    e.wr(SS, b"\xff" * (12 * N + 16))
    e.wr(CTX + 0x2C18, b"\x01\x02\x03\x04")
    e.run(0x18003820E, {0x180038218}, {UC_X86_REG_RSI: CTX})
    check("ResetRuntime tail: slotState rows 4..%d zero, rows 0..3 and the bytes after the table kept" % LAST,
          (e.rd(SS + 48, 12 * N - 48), e.rd(SS, 48), e.rd(SS + 12 * N, 16), e.rd(CTX + 0x2C18, 4)),
          (b"\0" * (12 * N - 48), b"\xff" * 48, b"\xff" * 16, b"\xff\xff\xff\xff"))
    # death arrays
    dsym = S.dsyms
    for nm, nb in (("d_pending", N), ("d_age", 4 * N), ("d_anim", N)):
        e.wr(dsym[nm], b"\xff" * 64)
    e.run(0x1800380A5, {0x1800380C3})
    pad = (4 * N + 15) // 16 * 16
    check("ResetRuntime: death arrays cleared (%d entries); the rest of their 64-byte slots untouched" % N,
          (e.rd(dsym["d_pending"], N), e.rd(dsym["d_age"], 4 * N), e.rd(dsym["d_anim"], N),
           e.rd(dsym["d_age"] + pad, 64 - pad), e.rd(dsym["d_pending"] + 16, 48), e.rd(dsym["d_anim"] + 16, 48)),
          (b"\0" * N, b"\0" * (4 * N), b"\0" * N, b"\xff" * (64 - pad), b"\xff" * 48, b"\xff" * 48))
    # stats rows: N = 8 in place at ctx+0x2B98, N = 9 in .t2r8 (descriptor)
    SB = STATS or (CTX + 0x2B98)
    e.wr(CTX + 0x2BF8, b"\x5a" * 16)               # the next match-state struct: must survive
    e.wr(SB, b"\xff" * (12 * N))
    uc.reg_write(UC_X86_REG_XMM0, 0)
    e.run(0x180061F06, {0x180061F1B}, {UC_X86_REG_RAX: CTX})
    check("new match clears stats rows 0..%d" % LAST, e.rd(SB, 12 * N), b"\0" * (12 * N))
    check("new match leaves ctx+0x2BF8.. (next match-state struct) alone", e.rd(CTX + 0x2BF8, 16), b"\x5a" * 16)
    # the readers / writers of the rows: kills++ / deaths++ (FUN_180061DD0), AddParts, scoreboard base: all rows incl. the last
    e.stub(0x18004BF70, lambda em, u: CTX)
    for slot in (0, 3, 4, LAST):
        e.wr(SB, b"\0" * (12 * N))
        e.wr(CTX + 0x2BF8, b"\x5a" * 16)
        try:
            e.call(0x180061DD0, slot, 0, 0)
        except Exception as ex:                    # (the function calls into the HUD: only its stats store matters here)
            pass
        row = e.rd(SB + 12 * slot, 12)
        check("kills++(%d) lands in row %d" % (slot, slot), (struct.unpack("<i", row[:4])[0], e.rd(CTX + 0x2BF8, 16)), (1, b"\x5a" * 16))
    # scoreboard row pointer arithmetic (static check of the 3 `add reg, imm32` + 8 `[..+disp32]` sites)
    if STATS:
        want = STATS - CTX                  # imm32 that turns ctx + slot * 12 into the new row
        imms = []
        for va in (0x180067A7C, 0x180067AB6, 0x180067B9F):
            ins = next(slots8._MD.disasm(e.rd(va, 8), va))
            imms.append(ins.operands[-1].imm)
        check("scoreboard row bases point at the moved stats table", imms, [want] * 3)
        dl = []
        for va, fld in ((0x180018EAF, 8), (0x180018EF6, 8), (0x180018F9C, 8), (0x180019265, 8), (0x18001C13D, 8), (0x180033BB0, 8), (0x180061DF2, 0), (0x180061E8B, 4)):
            ins = next(slots8._MD.disasm(e.rd(va, 8), va))
            dl.append(CTX + ins.disp - (STATS + fld))
        check("stats disp32 sites point at the moved table (+field)", dl, [0] * 8)
    print("fails:", len(FAILS))
    return 1 if FAILS else 0


ORIG_REV = os.environ.get("T2R_SLOTS8_ORIG", "3a9cef157")        # the commit with the 8-slot patch before it took a slot count


def identity8():
    """N = 8 must stay byte-identical to the original 8-slot patch: the pre-N slots8*.py (git ORIG_REV) and the current ones are applied to the
    same input DLL and the outputs compared. SKIPs when the revision is not in the repository."""
    import shutil
    import subprocess
    import tempfile
    repo = os.path.dirname(TOOLS)
    files = ["slots8.py", "slots8_players.py", "slots8_peers.py", "slots8_misc.py", "cave_link.py"]
    tmp = tempfile.mkdtemp(prefix="_s8orig_", dir=TOOLS)      # directly under tools/: cave_link finds tools/win/ext/msys64 and tools/t2rtmp.py from there
    try:
        for f in files:
            r = subprocess.run(["git", "show", "%s:tools/features/%s" % (ORIG_REV, f)], cwd=repo, capture_output=True)
            if r.returncode:
                print("SKIP identity8: git show %s:%s failed" % (ORIG_REV, f))
                return 0
            open(os.path.join(tmp, f), "wb").write(r.stdout)
        ref = os.path.join(tmp, "ref8.dll")
        r = subprocess.run([sys.executable, os.path.join(tmp, "slots8.py"), BASE, ref], capture_output=True, text=True)
        if r.returncode:
            print("FAIL identity8: the original patch did not run:", r.stdout[-300:], r.stderr[-300:])
            return 1
        new, _ = slots8.apply(open(BASE, "rb").read(), 8)
        old = open(ref, "rb").read()
        check("N = 8 output byte-identical to the original 8-slot patch (%s, %d bytes)" % (ORIG_REV, len(old)), new == old, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    ns = [int(a) for a in sys.argv[1:]] or [8, 9]
    rc = 0
    for n in ns:
        rc |= main(n)
    if 8 in ns:
        rc |= identity8()
    sys.exit(rc)
