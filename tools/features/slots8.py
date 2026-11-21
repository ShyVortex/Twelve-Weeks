"""8-player (4v4) support for the T2R client winmm.dll: net slots 0..7 instead of 0..3. The slot count is one parameter N
(env T2R_SLOTS, default 8; 9 = a 4v4 plus one more client, re/winmm-nslots.md); N = 8 is byte-identical to the original 8-slot patch.

  python slots8.py <in.dll> <out.dll> [N]      # apply to a built DLL (after winmm_patches + ext_loader)

winmm (the original mod's MP client) is the spec `net::session` compiled with kMaxNetPlayers = 4: the loops over the 4 peers /
4 net players are UNROLLED (fixed addresses per entry), the tables are 4 entries wide and the match state sits right behind them.
This module appends a section `.t2r8` (RWX) that holds the new 8-entry tables plus a code cave, and then edits winmm:

  * table relocation  : the peer table (0x180167CC0, 4 x 0x40A0), PA_SLOT (0x18013B2A0, 4 x 0x77E8), the net players (ctx+0x1C0,
                        4 x 0xA70) and the per-slot match state move into 8-entry storage; every reference is retargeted
  * unrolled chains   : the last entry's code is copied for entries 4..7 (copy_chain: rip-relative operands remapped)
  * bounds            : `cmp r, 3` / `cmp r, 4` guards and loop ends become 7 / 8
  * rewritten leaves  : small functions that cannot be patched in place are rewritten in the cave (GNU as Intel syntax,
                        cave_link.py resolves V_<hex> engine addresses and D_<name> table addresses)

Every edit states the original bytes and refuses to land on anything else (patch / hook).
"""
import os
import re
import struct
import sys

import capstone
from capstone import x86_const as X

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cave_link  # noqa: E402

IMAGE_BASE = 0x180000000
TEXT_LO, TEXT_HI = 0x180001000, 0x18009EF86
CODE_RESERVE = 0x40000
MAGIC = 0x38523254          # 'T2R8'
N_MIN, N_MAX = 8, 9         # supported slot counts: the spectator candidate list (FUN_1800344E0: own slot excluded, 8 ints in its 32-byte stack slot)
                            # holds N - 1 <= 8 entries, so 9 is the last N that fits; below 8 the in-place stats rows and the 4-wide leftovers differ
PROTO_BASE = 0x2A           # wire protocol version of N = 8 (the original 4-slot client: 0x29); N != 8 uses PROTO_BASE + (N - 8)


def nslots():
    """The slot count N from the environment (T2R_SLOTS, default 8)."""
    return int(os.environ.get("T2R_SLOTS", "8") or "8")


def proto_version(n):
    return PROTO_BASE + (n - 8)


def bump(n, v):
    """An original 4-slot bound / count `v` (3, 4, 2 ...) widened to N slots: v + (N - 4). N = 8 gives the constants of the 8-slot patch (3 -> 7, 4 -> 8)."""
    return v + (n - 4)


class Img:
    """The DLL file bytes with a VMA view (headers + sections parsed by hand: pefile would copy 400 MB)."""

    def __init__(self, data):
        self.d = bytearray(data)
        d = self.d
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[pe:pe + 4] == b"PE\0\0"
        self.pe = pe
        self.nsec = struct.unpack_from("<H", d, pe + 6)[0]
        self.optsz = struct.unpack_from("<H", d, pe + 20)[0]
        self.opt = pe + 24
        self.size_of_image = struct.unpack_from("<I", d, self.opt + 56)[0]
        self.size_of_headers = struct.unpack_from("<I", d, self.opt + 60)[0]
        self.salign = struct.unpack_from("<I", d, self.opt + 32)[0]
        self.falign = struct.unpack_from("<I", d, self.opt + 36)[0]
        self.secs = []
        so = self.opt + self.optsz
        for i in range(self.nsec):
            b = so + 40 * i
            name = bytes(d[b:b + 8]).rstrip(b"\0")
            vsz, va, rsz, rptr = struct.unpack_from("<IIII", d, b + 8)
            self.secs.append((name, va, vsz, rptr, rsz))
        self.sec_tab_end = so + 40 * self.nsec

    def off(self, va):
        rva = va - IMAGE_BASE
        for _, sva, vsz, rptr, rsz in self.secs:
            if sva <= rva < sva + max(vsz, rsz):
                if rva - sva >= rsz:
                    raise ValueError(f"{va:#x} is in the zero-filled tail of a section")
                return rptr + (rva - sva)
        raise ValueError(f"{va:#x} is not in any section")

    def rd(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def wr(self, va, b):
        o = self.off(va)
        self.d[o:o + len(b)] = b


_MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
_MD.detail = True


def decode(img, lo, hi):
    """Instructions tiling exactly [lo, hi) (raises if the range does not end on an instruction boundary)."""
    code = img.rd(lo, hi - lo)
    out = list(_MD.disasm(code, lo))
    if sum(i.size for i in out) != hi - lo:
        raise SystemExit(f"slots8: {lo:#x}-{hi:#x} does not decode into whole instructions")
    return out


def rip_target(i):
    if i.id == 0:
        return None
    for op in i.operands:
        if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
            return i.address + i.size + op.mem.disp
    return None


def branch_target(i):
    if i.id == 0:
        return None
    if i.mnemonic == "jmp" or i.mnemonic == "call" or (i.mnemonic.startswith("j") and i.mnemonic != "jmp"):
        if i.operands and i.operands[0].type == X.X86_OP_IMM:
            return i.operands[0].imm
    return None


def _cc_of(i):
    b = i.bytes
    if 0x70 <= b[0] <= 0x7F:
        return b[0] & 0xF
    if b[0] == 0x0F and 0x80 <= b[1] <= 0x8F:
        return b[1] & 0xF
    raise SystemExit(f"slots8: not a conditional jump at {i.address:#x}")


class Slots8:
    def __init__(self, data, n=8):
        if not N_MIN <= n <= N_MAX:
            raise SystemExit(f"slots8: N = {n} is not supported (the patch is checked for {N_MIN}..{N_MAX} slots)")
        self.N = n
        self.img = Img(data)
        im = self.img
        self.sec_rva = (im.size_of_image + im.salign - 1) // im.salign * im.salign
        self.base = IMAGE_BASE + self.sec_rva
        self.cave = cave_link.Cave(self.base)
        self.dbase = self.base + CODE_RESERVE
        self.dsyms = {}
        self.dsize = 0
        self.dinit = []                 # (offset, bytes)
        self.hooks = []                 # (va, n, label, orig bytes)
        self.touched = []               # (lo, hi) byte ranges rewritten by patch/hook (the table retarget skips them)
        self.relocs = []                # (name, old_lo, size, new_va)
        self.report = []                # (kind, va, note)
        self._targets = None
        self.data("desc", 0x100)        # descriptor the ext reads: see finalize()

    # ---- tables -------------------------------------------------------------------------------------------------------
    def data(self, name, size, align=64, init=None):
        off = (self.dsize + align - 1) // align * align
        self.dsyms[name] = self.dbase + off
        self.dsize = off + size
        if init:
            self.dinit.append((off, bytes(init)))
        return self.dbase + off

    # ---- analysis -----------------------------------------------------------------------------------------------------
    def targets(self):
        """Every address some branch (direct, or through a switch table) can jump to; cached."""
        if self._targets is None:
            im = self.img
            code = im.rd(TEXT_LO, TEXT_HI - TEXT_LO)
            md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
            md.detail = True
            md.skipdata = True
            tg = {}
            prev = []
            for i in md.disasm(code, TEXT_LO):
                prev.append(i)
                if len(prev) > 8:
                    prev.pop(0)
                t = branch_target(i)
                if t is not None:
                    tg.setdefault(t, []).append(i.address)
                if i.id and i.mnemonic == "movsxd" and "*4]" in i.op_str:
                    m = re.search(r"\[(\w+) \+ \w+\*4\]", i.op_str)
                    if m:
                        for q in reversed(prev[:-1]):
                            if q.mnemonic == "lea" and q.op_str.startswith(m.group(1) + ", [rip"):
                                T = rip_target(q)
                                k = 0
                                while True:
                                    v = struct.unpack("<i", im.rd(T + 4 * k, 4))[0]
                                    t2 = T + v
                                    if not (q.address - 0x8000 <= t2 < q.address + 0x8000) or not (TEXT_LO <= t2 < TEXT_HI):
                                        break
                                    tg.setdefault(t2, []).append(-1)
                                    k += 1
                                    if k > 400:
                                        break
                                break
            self._targets = tg
        return self._targets

    def targets_inside(self, lo, hi):
        """Addresses strictly inside (lo, hi) that something OUTSIDE [lo, hi) can branch to (switch tables count as outside)."""
        tg = self.targets()
        return sorted(t for t, srcs in tg.items() if lo < t < hi and any(not (lo <= a < hi) for a in srcs))

    # ---- editing ------------------------------------------------------------------------------------------------------
    def patch(self, va, orig, new, note, kind="byte"):
        orig = bytes.fromhex(orig.replace(" ", "")) if isinstance(orig, str) else bytes(orig)
        new = bytes.fromhex(new.replace(" ", "")) if isinstance(new, str) else bytes(new)
        assert len(orig) == len(new), f"patch {va:#x}: length differs"
        cur = self.img.rd(va, len(orig))
        if cur != orig:
            raise SystemExit(f"slots8: {note}: unexpected bytes at {va:#x}: {cur.hex(' ')} (expected {orig.hex(' ')})")
        self.touched.append((va, va + len(orig)))
        self.report.append((kind, va, note))
        self.img.wr(va, new)

    def hook(self, va, n, label, note, allow_inner=()):
        """Replace the whole instructions in [va, va+n) by `jmp label` (+ nops); the cave must contain the displaced code."""
        assert n >= 5
        decode(self.img, va, va + n)
        inner = [t for t in self.targets_inside(va, va + n) if t not in allow_inner]
        if inner:
            raise SystemExit(f"slots8: hook {va:#x}+{n} ({note}): branch targets inside the hooked bytes: {[hex(t) for t in inner]}")
        self.hooks.append((va, n, label, self.img.rd(va, n), "jmp"))
        self.touched.append((va, va + n))
        self.report.append(("hook", va, note))

    def _one(self, va):
        i = next(_MD.disasm(self.img.rd(va, 16), va))
        return i

    def patch_imm(self, va, old, new, note, mnem=None):
        """Change the immediate of the instruction at va (must be `old`)."""
        i = self._one(va)
        if mnem and i.mnemonic != mnem:
            raise SystemExit(f"slots8: {note}: {va:#x} is `{i.mnemonic} {i.op_str}`, expected {mnem}")
        if i.imm_size == 0 or i.operands[-1].type != X.X86_OP_IMM or i.operands[-1].imm != old:
            raise SystemExit(f"slots8: {note}: {va:#x} `{i.mnemonic} {i.op_str}` has no immediate {old}")
        o, sz = i.imm_offset, i.imm_size
        cur = bytes(i.bytes)
        nb = bytearray(cur)
        nb[o:o + sz] = int(new).to_bytes(sz, "little", signed=new < 0)
        self.patch(va, cur, bytes(nb), note)

    def patch_disp(self, va, old, new, note):
        """Change the disp32 of the (non rip-relative) memory operand of the instruction at va (must be `old`)."""
        i = self._one(va)
        if i.disp_size != 4 or i.disp != old or rip_target(i) is not None:
            raise SystemExit(f"slots8: {note}: {va:#x} `{i.mnemonic} {i.op_str}` has no disp32 {old:#x}")
        if not -(1 << 31) <= new < (1 << 31):
            raise SystemExit(f"slots8: {note}: new disp out of range")
        cur = bytes(i.bytes)
        nb = bytearray(cur)
        struct.pack_into("<i", nb, i.disp_offset, new)
        self.patch(va, cur, bytes(nb), note)

    def hook_entry(self, va, label, note, minbytes=5):
        """hook() over the first whole instructions of a function (>= minbytes)."""
        n = 0
        for i in _MD.disasm(self.img.rd(va, 32), va):
            n += i.size
            if n >= minbytes:
                break
        self.hook(va, n, label, note)
        return n

    def retarget_calls(self, sites, old, new, note):
        """call/jmp rel32 at each of `sites` (VMA of the opcode) from `old` to `new` (a VA or a cave label)."""
        for va in sites:
            b = self.img.rd(va, 5)
            if b[0] not in (0xE8, 0xE9):
                raise SystemExit(f"slots8: {va:#x}: not a rel32 call/jmp")
            t = va + 5 + struct.unpack("<i", b[1:])[0]
            if t != old:
                raise SystemExit(f"slots8: {va:#x}: calls {t:#x}, expected {old:#x}")
            self.hooks.append((va, 5, new, bytes(b), "keep"))
            self.touched.append((va, va + 5))
        self.report.append(("call", sites[0], f"{note} ({len(sites)} sites)"))

    def relocate_table(self, name, old_lo, size, new_va):
        self.relocs.append((name, old_lo, size, new_va))

    # ---- emission helpers (raw instruction copies) --------------------------------------------------------------------
    def label(self, name):
        if name in self.cave.labels:
            raise SystemExit(f"duplicate label {name}")
        self.cave.align(1)
        self.cave.labels[name] = self.base + len(self.cave.code)

    def sym_off(self, off, sym, kind="rel32", extra=0):
        self.cave.relocs.append((off, 4 + extra, sym, 0))

    def emit_jmp(self, sym):
        off = len(self.cave.code)
        self.cave.code += b"\xe9\0\0\0\0"
        self.cave.relocs.append((off + 1, 4, sym, 0))

    def emit_branch(self, i, sym):
        c = self.cave
        off = len(c.code)
        if i.mnemonic == "jmp":
            c.code += b"\xe9\0\0\0\0"
            c.relocs.append((off + 1, 4, sym, 0))
        elif i.mnemonic == "call":
            c.code += b"\xe8\0\0\0\0"
            c.relocs.append((off + 1, 4, sym, 0))
        else:
            c.code += bytes([0x0F, 0x80 + _cc_of(i), 0, 0, 0, 0])
            c.relocs.append((off + 2, 4, sym, 0))

    def emit_insn(self, i, rip_to=None, imm=None, disp_add=0):
        """Append instruction `i` (rip-relative operand re-pointed to `rip_to`; immediate replaced by `imm`; disp32 += disp_add)."""
        c = self.cave
        b = bytearray(i.bytes)
        if imm is not None:
            o, sz = i.imm_offset, i.imm_size
            b[o:o + sz] = int(imm).to_bytes(sz, "little", signed=(imm < 0))
        rt = rip_target(i)
        if rt is not None:
            do = i.disp_offset
            b[do:do + 4] = b"\0\0\0\0"
            trailing = len(b) - do - 4
            off = len(c.code)
            c.code += b
            c.relocs.append((off + do, 4 + trailing, "V_%x" % (rip_to if rip_to is not None else rt), 0))
        else:
            if disp_add:
                assert i.disp_size == 4, f"{i.address:#x}: disp shift needs a disp32"
                do = i.disp_offset
                v = struct.unpack_from("<i", b, do)[0] + disp_add
                struct.pack_into("<i", b, do, v)
            c.code += b

    def asm(self, text, name=None):
        return self.cave.add(text, name)

    # ---- unrolled chain extension -------------------------------------------------------------------------------------
    def remap_rip(self, t):
        """Where a rip-relative target lives after the table relocations (identity outside the tables)."""
        for _, lo, size, new in self.relocs:
            if lo <= t < lo + size:
                return new + (t - lo)
        return t

    def copy_chain(self, name, hook, tmpl, win_lo, stride, new_lo, tmpl_entry, first, count=None, next_targets=(),
                   last_exit=None, fall="next", end=None, slot_imm=(), rec_disp=None, rec_delta=0, note="", allow_inner=()):
        """Extend an unrolled per-entry code block to entries first .. count-1.

        hook=(lo, hi)  : the original code that is replaced by a jump into the cave (the block of entry `first`, or the part of
                         the chain that is re-generated);
        tmpl=(lo, hi)  : the template block copied once per entry j (usually == hook; a non-destructive earlier block when the
                         last original block reuses registers);
        win_lo         : start of the template entry's window in the OLD table (stride bytes); rip-relative operands that fall
                         in it move to new_lo + j*stride + offset; any other operand into a relocated table is remapped;
        rec_disp=(lo, hi): [reg + disp32] operands with disp in the template entry's window of the net player records
                         (relative to the match context) shift by (j - tmpl_entry) * stride;
        next_targets   : branch targets that mean "this entry does not apply, try the next" -> next copy (the last copy goes to
                         last_exit, default: unchanged);
        fall == 'next' : copies run in sequence, a branch to `end` (the template's fall-through address, default tmpl[1]) goes
                         to the next copy and the last copy continues at `end`;
                'end'  : every copy continues at `end` (entry found / handled);
        slot_imm       : addresses of template instructions whose immediate (== tmpl_entry) becomes j.
        """
        count = self.N if count is None else count
        tins = decode(self.img, tmpl[0], tmpl[1])
        trng = {i.address for i in tins}
        end = end if end is not None else tmpl[1]
        lbl = "S8_" + name
        self.hook(hook[0], hook[1] - hook[0], lbl, note or name, allow_inner=allow_inner)
        self.cave.align(16)
        self.label(lbl)
        nxt = set(next_targets)
        for j in range(first, count):
            self.label(f"{lbl}_{j}")
            last = j + 1 >= count
            for i in tins:
                self.label(f"{lbl}_{j}_{i.address:x}")
                t = branch_target(i)
                if t is not None:
                    if i.mnemonic == "call":
                        self.emit_branch(i, "V_%x" % t)
                        continue
                    if t in trng:
                        sym = f"{lbl}_{j}_{t:x}"
                    elif t in nxt:
                        sym = ("V_%x" % (last_exit if last_exit is not None else t)) if last else f"{lbl}_{j + 1}"
                    elif t == end:
                        sym = ("V_%x" % t) if fall == "end" else (("V_%x" % t) if last else f"{lbl}_{j + 1}")
                    else:
                        sym = "V_%x" % t
                    self.emit_branch(i, sym)
                    continue
                rt = rip_target(i)
                rip_to = None
                if rt is not None:
                    if win_lo <= rt < win_lo + stride:
                        rip_to = new_lo + j * stride + (rt - win_lo)
                    else:
                        rip_to = self.remap_rip(rt)
                da = 0
                if rec_disp and rt is None and i.disp_size == 4 and rec_disp[0] <= i.disp < rec_disp[1]                         and not any(op.type == X.X86_OP_MEM and op.mem.base in (X.X86_REG_RSP, X.X86_REG_RBP) for op in i.operands):
                    da = rec_delta + (j - tmpl_entry) * stride
                imm = j if i.address in slot_imm else None
                self.emit_insn(i, rip_to=rip_to, imm=imm, disp_add=da)
            if fall == "end":
                self.emit_jmp("V_%x" % end)
        if fall == "next":
            self.emit_jmp("V_%x" % end)

    # ---- finalize -----------------------------------------------------------------------------------------------------
    def _apply_relocs(self):
        """Retarget every rip-relative reference into a relocated table (instructions not rewritten by patch/hook)."""
        im = self.img
        code = im.rd(TEXT_LO, TEXT_HI - TEXT_LO)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        md.skipdata = True
        touched = sorted(self.touched)
        counts = {n: 0 for n, *_ in self.relocs}
        for i in md.disasm(code, TEXT_LO):
            rt = rip_target(i)
            if rt is None:
                continue
            for name, lo, size, new in self.relocs:
                if lo <= rt < lo + size:
                    if any(a <= i.address < b or a < i.address + i.size <= b for a, b in touched):
                        continue
                    newt = new + (rt - lo)
                    disp = newt - (i.address + i.size)
                    if not -(1 << 31) <= disp < (1 << 31):
                        raise SystemExit("retarget out of range")
                    im.wr(i.address + i.disp_offset, struct.pack("<i", disp))
                    counts[name] += 1
        for name, n in counts.items():
            self.report.append(("table", 0, f"{name}: {n} rip-relative references retargeted"))
        return counts

    def finalize(self):
        im = self.img
        counts = self._apply_relocs()
        # descriptor for the ext (offset 0 of the data area): magic, version, then the table bases. Version 1 = N = 8 (the original 8-slot
        # patch, unchanged bytes); version 2 (N != 8) appends u32 N, u32 protocol version, u64 stats rows base (0 = in place at ctx+0x2B98).
        d = struct.pack("<II", MAGIC, 1 if self.N == 8 else 2)
        for k in ("peers", "pa_slot", "players", "slotstate"):
            d += struct.pack("<Q", self.dsyms.get(k, 0))
        if self.N != 8:
            d += struct.pack("<IIQ", self.N, proto_version(self.N), self.dsyms.get("stats", 0))
        self.dinit.append((0, d))
        code_all = self.cave.link(self.dsyms)
        if len(code_all) > CODE_RESERVE:
            raise SystemExit(f"slots8: cave is {len(code_all):#x} bytes, reserve {CODE_RESERVE:#x}")
        # hooks (jump into the cave / call retarget)
        for va, n, label, orig, mode in self.hooks:
            tgt = label if isinstance(label, int) else self.cave.labels[label]
            cur = im.rd(va, n)
            if cur != orig:
                raise SystemExit(f"slots8: bytes changed under hook at {va:#x}")
            if mode == "keep":                                      # retargeted call/jmp keeps its opcode
                b = bytes([orig[0]]) + struct.pack("<i", tgt - (va + 5))
            else:
                b = b"\xe9" + struct.pack("<i", tgt - (va + 5)) + b"\x90" * (n - 5)
            im.wr(va, b)
        # the new section
        data = bytearray(self.dsize)
        for off, b in self.dinit:
            data[off:off + len(b)] = b
        used = len(data)
        while used and data[used - 1] == 0:
            used -= 1
        raw = bytearray(code_all) + b"\xcc" * (CODE_RESERVE - len(code_all)) + data[:used]
        fa = im.falign
        raw_size = (len(raw) + fa - 1) // fa * fa
        raw += b"\0" * (raw_size - len(raw))
        vsize = CODE_RESERVE + self.dsize
        sa = im.salign
        so = im.sec_tab_end
        assert so + 40 <= im.size_of_headers, "no room for another section header"
        raw_ptr = (len(im.d) + fa - 1) // fa * fa
        d = im.d
        d += b"\0" * (raw_ptr - len(d))
        d += raw
        d[so:so + 40] = struct.pack("<8sIIIIIIHHI", b".t2r8", vsize, self.sec_rva, raw_size, raw_ptr, 0, 0, 0, 0, 0xE0000020)
        struct.pack_into("<H", d, im.pe + 6, im.nsec + 1)
        struct.pack_into("<I", d, im.opt + 56, (self.sec_rva + vsize + sa - 1) // sa * sa)
        return bytes(d), counts


def build_all(S):
    import slots8_players
    import slots8_peers
    import slots8_misc
    for m in (slots8_players, slots8_peers, slots8_misc):
        m.build(S)


def apply(data, n=None):
    S = Slots8(data, nslots() if n is None else n)
    build_all(S)
    out, _ = S.finalize()
    return out, S


if __name__ == "__main__":
    src, dst = sys.argv[1:3]
    out, S = apply(open(src, "rb").read(), int(sys.argv[3]) if len(sys.argv) > 3 else None)
    open(dst, "wb").write(out)
    for k, va, note in S.report:
        print(f"{k:6s} {va:#x} {note}")
    print(f"{dst}: .t2r8 added, N = {S.N}, cave {len(S.cave.code):#x} bytes, data {S.dsize:#x} bytes, {len(S.report)} sites")
