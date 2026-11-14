"""LLVM 3.7 bitstream (DXIL) round-trip reader / writer with function-body edits.

Used by p1_abi.py (Program: operands -> new i32 constants, literal edits such as extractvalue indices, inserted dx.op calls,
module-level i32 constant values; value numbering, phi / switch operands, the function VST and the METADATA_ATTACHMENT
instruction ordinals are redone) and by the superseded p1_shader_fix.py (retarget).  The writer re-emits every block /
abbreviation / record exactly as read (an unmodified module round-trips bit-identically - checked by selftest(); all 1 216
Bookstore programs), so the only change is the edit.  Old single-purpose entry point:

  retarget(bitcode, edits) where edits = [(call ordinal, arg index, new i32 value)]
    - appends the needed i32 constants at the end of the function's CONSTANTS_BLOCK (SETTYPE i32 first if needed),
    - shifts every instruction operand that refers to a value numbered before the function's instructions by the number of
      inserted constants (LLVM 3.7 relative operand encoding: rel = InstNum - ValNo), absolute ones (switch case values,
      alloca size) by the same rule,
    - points the chosen call operands at the new constants.

Value numbering: module globals / functions / aliases / module constants, then per function: arguments, function constants,
then every value-producing instruction (calls producing void and br / ret / store / switch / unreachable produce none).
"""
import collections
import struct

# ---------------------------------------------------------------- bit reader / writer


class Reader:
    def __init__(self, data, pos=0):
        self.d = bytes(data) + b"\0" * 16          # padding: read() takes 16 bytes at a time
        self.pos = pos

    def read(self, n):
        if n == 0:
            return 0
        p = self.pos
        v = (int.from_bytes(self.d[p >> 3:(p >> 3) + 16], "little") >> (p & 7)) & ((1 << n) - 1)   # n <= 64
        self.pos = p + n
        return v

    def vbr(self, n):
        v, sh, hi = 0, 0, 1 << (n - 1)
        while True:
            x = self.read(n)
            v |= (x & (hi - 1)) << sh
            sh += n - 1
            if not x & hi:
                return v

    def align32(self):
        self.pos = (self.pos + 31) & ~31


class Writer:
    """little-endian bit writer: whole bytes go to `out`, the partial byte stays in (cur, nbits)"""
    def __init__(self):
        self.out = bytearray()
        self.cur = 0
        self.nbits = 0

    def tell(self):
        return 8 * len(self.out) + self.nbits

    def write(self, v, n):
        self.cur |= (v & ((1 << n) - 1)) << self.nbits
        self.nbits += n
        while self.nbits >= 8:
            self.out.append(self.cur & 0xFF)
            self.cur >>= 8
            self.nbits -= 8

    def vbr(self, v, n):
        hi = n - 1
        while True:
            chunk = v & ((1 << hi) - 1)
            v >>= hi
            self.write(chunk | ((1 << hi) if v else 0), n)
            if not v:
                return

    def align32(self):
        r = self.tell() % 32
        if r:
            self.write(0, 32 - r)

    def patch32(self, bitpos, value):
        """overwrite an aligned 32-bit word already written (block length back-patch)"""
        assert bitpos % 32 == 0 and bitpos + 32 <= 8 * len(self.out)
        struct.pack_into("<I", self.out, bitpos // 8, value)

    def tobytes(self):
        self.align32()
        return bytes(self.out)


# ---------------------------------------------------------------- tree


class Block:
    def __init__(self, bid, width):
        self.bid, self.width, self.items = bid, width, []


class Rec:
    """abbrev: None (unabbreviated) or the abbrev op list; ops: list of int values (blob = bytes)"""
    def __init__(self, aid, abbrev, code, ops):
        self.aid, self.abbrev, self.code, self.ops = aid, abbrev, code, ops


class AbbrevDef:
    def __init__(self, ops):
        self.ops = ops


def _read_scalar(r, kind, w):
    if kind == "fixed":
        return r.read(w)
    if kind == "vbr":
        return r.vbr(w)
    if kind == "char6":
        return r.read(6)
    raise ValueError(kind)


def parse(data):
    """data = bitcode bytes -> list of top-level Blocks"""
    r = Reader(data, 32)
    blockinfo = {}

    def block(bid, width, abbrevs):
        blk = Block(bid, width)
        info_bid = None
        while True:
            if bid is None and r.pos + 32 > 8 * len(data):
                return blk
            aid = r.read(width)
            if aid == 0:
                r.align32()
                return blk
            if aid == 1:
                nb = r.vbr(8)
                nw = r.vbr(4)
                r.align32()
                r.read(32)
                blk.items.append(block(nb, nw, list(blockinfo.get(nb, []))))
                continue
            if aid == 2:
                n = r.vbr(5)
                ops = []
                for _ in range(n):
                    if r.read(1):
                        ops.append(("lit", r.vbr(8)))
                    else:
                        e = r.read(3)
                        if e in (1, 2):
                            ops.append(("fixed" if e == 1 else "vbr", r.vbr(5)))
                        else:
                            ops.append(({3: "array", 4: "char6", 5: "blob"}[e], None))
                if bid == 0:
                    blockinfo.setdefault(info_bid, []).append(ops)
                else:
                    abbrevs.append(ops)
                blk.items.append(AbbrevDef(ops))
                continue
            if aid == 3:
                code = r.vbr(6)
                n = r.vbr(6)
                ops = [r.vbr(6) for _ in range(n)]
                if bid == 0 and code == 1:
                    info_bid = ops[0]
                blk.items.append(Rec(3, None, code, ops))
                continue
            ab = abbrevs[aid - 4]
            vals = []
            j = 0
            while j < len(ab):
                kind, w = ab[j]
                if kind == "lit":
                    vals.append(w)
                elif kind == "array":
                    n = r.vbr(6)
                    ek, ew = ab[j + 1]
                    vals.append([_read_scalar(r, ek, ew) for _ in range(n)])
                    j += 1
                elif kind == "blob":
                    n = r.vbr(6)
                    r.align32()
                    vals.append(bytes(r.read(8) for _ in range(n)))
                    r.align32()
                else:
                    vals.append(_read_scalar(r, kind, w))
                j += 1
            code = vals[0]
            if bid == 0 and code == 1:
                info_bid = vals[1]
            blk.items.append(Rec(aid, ab, code, vals))

    top = block(None, 2, [])
    return top


def emit(top):
    w = Writer()
    w.write(0x42, 8)
    w.write(0x43, 8)
    w.write(0xC0, 8)
    w.write(0xDE, 8)

    def block_body(blk):
        for it in blk.items:
            if isinstance(it, Block):
                w.write(1, blk.width)
                w.vbr(it.bid, 8)
                w.vbr(it.width, 4)
                w.align32()
                at = w.tell()
                w.write(0, 32)
                start = w.tell()
                block_body(it)
                w.write(0, it.width)        # END_BLOCK
                w.align32()
                w.patch32(at, (w.tell() - start) // 32)
            elif isinstance(it, AbbrevDef):
                w.write(2, blk.width)
                w.vbr(len(it.ops), 5)
                for kind, val in it.ops:
                    if kind == "lit":
                        w.write(1, 1)
                        w.vbr(val, 8)
                    else:
                        w.write(0, 1)
                        w.write({"fixed": 1, "vbr": 2, "array": 3, "char6": 4, "blob": 5}[kind], 3)
                        if kind in ("fixed", "vbr"):
                            w.vbr(val, 5)
            else:
                w.write(it.aid, blk.width)
                if it.abbrev is None:
                    w.vbr(it.code, 6)
                    w.vbr(len(it.ops), 6)
                    for v in it.ops:
                        w.vbr(v, 6)
                    continue
                ab = it.abbrev
                j = k = 0
                while j < len(ab):
                    kind, wd = ab[j]
                    v = it.ops[k]
                    if kind == "lit":
                        pass
                    elif kind == "array":
                        ek, ew = ab[j + 1]
                        w.vbr(len(v), 6)
                        for x in v:
                            _write_scalar(w, ek, ew, x)
                        j += 1
                    elif kind == "blob":
                        w.vbr(len(v), 6)
                        w.align32()
                        for byte in v:
                            w.write(byte, 8)
                        w.align32()
                    else:
                        _write_scalar(w, kind, wd, v)
                    j += 1
                    k += 1
    block_body(top)
    return w.tobytes()


def _write_scalar(w, kind, wd, v):
    if kind == "fixed":
        w.write(v, wd)
    elif kind == "vbr":
        w.vbr(v, wd)
    elif kind == "char6":
        w.write(v, 6)


def flat_ops(rec):
    """record operands as a flat list (abbreviated: literal code dropped, arrays flattened) + a setter"""
    if rec.abbrev is None:
        return list(rec.ops)
    out = []
    for v in rec.ops[1:]:
        out.extend(v if isinstance(v, list) else [v])
    return out


def set_flat(rec, vals):
    """write a (same length) flat operand list back; an abbreviated record whose values no longer fit its fixed fields is
    turned into an unabbreviated one"""
    if rec.abbrev is None:
        rec.ops = list(vals)
        return
    new = [rec.ops[0]]
    i = 0
    ok = True
    for (kind, wd), v in zip(_abbrev_scalars(rec.abbrev), rec.ops[1:]):
        if isinstance(v, list):
            new.append(vals[i:i + len(v)])
            i += len(v)
        else:
            new.append(vals[i])
            if kind == "fixed" and vals[i] >= (1 << wd):
                ok = False
            if kind == "lit" and vals[i] != v:
                ok = False
            i += 1
    if ok:
        rec.ops = new
    else:
        rec.aid, rec.abbrev, rec.ops = 3, None, list(vals)


def _abbrev_scalars(ab):
    out = []
    j = 0
    while j < len(ab):
        if ab[j][0] == "array":
            out.append(("array", ab[j + 1]))
            j += 2
        else:
            out.append(ab[j])
            j += 1
    return out[1:]      # first op is the record code


# ---------------------------------------------------------------- module model: types, values, the function body

MODULE, PARAMATTR, TYPE, CONST, FUNC, BLOCKINFO = 8, 9, 17, 11, 12, 0


def sub(blk, bid):
    return [x for x in blk.items if isinstance(x, Block) and x.bid == bid]


def recs(blk):
    return [x for x in blk.items if isinstance(x, Rec)]


class Module:
    def __init__(self, top):
        self.top = top
        self.mod = sub(top, MODULE)[0]
        self.types = []
        for t in sub(self.mod, TYPE):
            for r in recs(t):
                if r.code not in (1, 19):          # NUMENTRY, STRUCT_NAME define no type
                    self.types.append((r.code, flat_ops(r)))
        self.n_global = 0
        self.func_decls = []        # (value id, type id, is proto)
        for r in recs(self.mod):
            ops = flat_ops(r)
            if r.code == 7:                     # GLOBALVAR
                self.n_global += 1
            elif r.code == 8:                   # FUNCTION [type, cc, isproto, ...]
                self.func_decls.append((self.n_global, ops[0], ops[2]))
                self.n_global += 1
            elif r.code in (9, 14):             # ALIAS
                self.n_global += 1
        self.n_modconst = 0
        for c in sub(self.mod, CONST):
            self.n_modconst += sum(1 for r in recs(c) if r.code != 1)
        self.value_types = {}
        for vid, ty, proto in self.func_decls:
            self.value_types[vid] = ty

    def i32_type(self):
        for i, (code, ops) in enumerate(self.types):
            if code == 7 and ops and ops[0] == 32:
                return i
        return None

    def fn_return_void(self, fnty):
        code, ops = self.types[fnty]
        # FUNCTION type record (code 21): [vararg, retty, params...]
        if code == 21:
            rt = ops[1]
        else:
            return False
        return self.types[rt][0] == 2           # VOID = 2

    def fn_param_count(self, fnty):
        code, ops = self.types[fnty]
        return len(ops) - 2 if code == 21 else 0


# instruction codes (LLVM 3.7 FUNC_CODE_INST_*)
VOID_CODES = {10, 11, 12, 13, 15, 31, 36, 44, 35, 33, 1}     # ret br switch indirectbr unreachable resume fence store debugloc


class Inst:
    """one function-body record: code, flat operands, its InstNum, the value id it defines (None = no value), refs
    [(flat index, kind)], the value ids those refs name (None for 'abs' / 'relsigned'), call info for CALL records"""
    __slots__ = ("idx", "rec", "code", "ops", "num", "vid", "refs", "ref_ids", "call")

    def __init__(self, idx, rec, code, ops, num, vid, refs, ref_ids, call):
        self.idx, self.rec, self.code, self.ops, self.num, self.vid = idx, rec, code, ops, num, vid
        self.refs, self.ref_ids, self.call = refs, ref_ids, call


class Program:
    """parsed DXIL module with its single function body laid out (value numbering resolved)"""

    def __init__(self, bitcode):
        self.top = top = parse(bitcode)
        self.m = m = Module(top)
        funcs = sub(m.mod, FUNC)
        if len(funcs) != 1:
            raise ValueError("expected one function body, got %d" % len(funcs))
        self.fb = fb = funcs[0]
        body_fn = [f for f in m.func_decls if f[2] == 0]
        if len(body_fn) != 1:
            raise ValueError("expected one defined function")
        nargs = m.fn_param_count(body_fn[0][1])
        base = m.n_global + m.n_modconst + nargs
        fconsts = sub(fb, CONST)
        if len(fconsts) > 1:
            raise ValueError("several function constant blocks")
        self.fconsts = fconsts[0] if fconsts else None
        cvals = self._consts(recs(self.fconsts)) if self.fconsts else []
        mvals = []
        for c in sub(m.mod, CONST):
            mvals += self._consts(recs(c))
        self.base, self.first_inst = base, base + len(cvals)
        self.cvals, self.mvals = cvals, mvals
        self.insts = []
        num = self.first_inst
        for idx, r in enumerate(it for it in fb.items if isinstance(it, Rec)):
            ops = flat_ops(r)
            refs = []
            produces = r.code not in VOID_CODES
            c = r.code
            call = None
            if c == 34:                        # CALL [attrs, cc, (fmf), fnty, fnid(+ty), args...]
                cc = ops[1]
                i = 2
                if cc & (1 << 17):
                    i += 1
                explicit = cc & (1 << 15)
                fnty = ops[i] if explicit else None
                i += 1 if explicit else 0
                refs.append((i, "rel"))
                fnid = num - ops[i]
                i += 1
                nparams = m.fn_param_count(fnty) if fnty is not None else len(ops) - i
                args = []
                for a in range(nparams):
                    refs.append((i + a, "rel"))
                    args.append(num - ops[i + a])
                produces = not m.fn_return_void(fnty) if fnty is not None else True
                call = (fnid, args, [self.const_of(x) for x in args], i)
            elif c == 2:                        # BINOP [a(+ty), b, opcode, (flags)]
                refs += [(0, "rel"), (1, "rel")]
            elif c == 3:                        # CAST [a(+ty), destty, opc]
                refs.append((0, "rel"))
            elif c == 26:                       # EXTRACTVAL [agg(+ty), idx...]
                refs.append((0, "rel"))
            elif c == 27:                       # INSERTVAL [agg(+ty), val(+ty), idx...]
                refs += [(0, "rel"), (1, "rel")]
            elif c in (28, 9):                  # CMP2 [a(+ty), b, pred]
                refs += [(0, "rel"), (1, "rel")]
            elif c == 29:                       # VSELECT [t(+ty), f, cond(+ty)]
                refs += [(0, "rel"), (1, "rel"), (2, "rel")]
            elif c == 10:                       # RET [val(+ty)]?
                if ops:
                    refs.append((0, "rel"))
            elif c == 11:                       # BR [bb, bb, cond]
                if len(ops) == 3:
                    refs.append((2, "rel"))
            elif c == 16:                       # PHI [ty, val(signed rel), bb, ...]
                for k in range(1, len(ops) - 1, 2):
                    refs.append((k, "relsigned"))
            elif c == 20:                       # LOAD [ptr(+ty), ty, align, vol]
                refs.append((0, "rel"))
            elif c == 44:                       # STORE [ptr(+ty), val(+ty), align, vol]
                refs += [(0, "rel"), (1, "rel")]
            elif c == 43:                       # GEP [inbounds, ty, ptr(+ty), idx(+ty)...]
                for k in range(2, len(ops)):
                    refs.append((k, "rel"))
            elif c == 6:                        # EXTRACTELT [vec(+ty), idx(+ty)]
                refs += [(0, "rel"), (1, "rel")]
            elif c == 7:                        # INSERTELT [vec(+ty), val, idx(+ty)]
                refs += [(0, "rel"), (1, "rel"), (2, "rel")]
            elif c == 8:                        # SHUFFLEVEC [v1(+ty), v2, mask]
                refs += [(0, "rel"), (1, "rel"), (2, "rel")]
            elif c == 12:                       # SWITCH [opty, cond, default, (caseval abs, bb)...]
                refs.append((1, "rel"))
                for k in range(3, len(ops) - 1, 2):
                    refs.append((k, "abs"))
            elif c == 19:                       # ALLOCA [instty, opty, op abs, align]
                refs.append((2, "abs"))
            elif c in (1, 35, 33, 15):
                pass
            else:
                raise ValueError("unsupported instruction code %d" % c)
            for k, kind in refs:
                if kind == "rel" and ops[k] > num:
                    raise ValueError("forward reference in code %d" % c)
            ref_ids = [num - ops[k] if kind == "rel" else None for k, kind in refs]
            self.insts.append(Inst(idx, r, c, ops, num, num if produces else None, refs, ref_ids, call))
            if produces:
                num += 1
        self.by_vid = {it.vid: it for it in self.insts if it.vid is not None}

    @staticmethod
    def _consts(rs):
        out, cur = [], None
        for r in rs:
            ops = flat_ops(r)
            if r.code == 1:
                cur = ops[0]
                continue
            v = None
            if r.code == 4:
                v = (ops[0] >> 1) * (-1 if ops[0] & 1 else 1)
            elif r.code == 2:                   # NULL = 0
                v = 0
            out.append((cur, v))
        return out

    def const_of(self, vid):
        """integer value of a constant value id (module or function constant), else None"""
        m = self.m
        if m.n_global <= vid < m.n_global + m.n_modconst:
            return self.mvals[vid - m.n_global][1]
        if self.base <= vid < self.first_inst:
            return self.cvals[vid - self.base][1]
        return None

    def calls(self, opcode=None):
        """CALL instructions whose first argument is the dx.op opcode `opcode` (all calls when None)"""
        out = []
        for it in self.insts:
            if it.call and (opcode is None or (it.call[2] and it.call[2][0] == opcode)):
                out.append(it)
        return out

    def users(self, vid):
        return [it for it in self.insts if vid in it.ref_ids]

    # ---------------------------------------------------------------- module-level in-place edits (no renumbering)
    def set_module_int(self, old, new, bits=32):
        """change the value of the module-level i<bits> INTEGER constant `old` in place (constants are uniqued: one record).
        Returns the number of records changed (0 if the module has no such constant)."""
        it = None
        for i, (code, ops) in enumerate(self.m.types):
            if code == 7 and ops and ops[0] == bits:
                it = i
        n = 0
        for c in sub(self.m.mod, CONST):
            cur = None
            for r in recs(c):
                ops = flat_ops(r)
                if r.code == 1:
                    cur = ops[0]
                    continue
                if r.code == 4 and cur == it and ops[0] == _sv(old):
                    set_flat(r, [_sv(new)] + ops[1:])
                    n += 1
        return n

    def set_array_len(self, old, new):
        """ARRAY type records [numelts, eltty] with numelts == old -> new (TYPE block, in place). Returns how many."""
        n = 0
        for t in sub(self.m.mod, TYPE):
            for r in recs(t):
                ops = flat_ops(r)
                if r.code == 11 and ops and ops[0] == old:
                    set_flat(r, [new] + ops[1:])
                    n += 1
        return n

    # ---------------------------------------------------------------- function body edits
    def emit(self, const_edits=(), lit_edits=(), inserts=(), ref_edits=()):
        """Re-encode the module with function-body edits.  Returns bitcode.
          const_edits = [(Inst, flat op index of a 'rel' ref, i32 value)]: the operand is pointed at a NEW i32 function constant
          lit_edits   = [(Inst, flat op index, literal)]                   (e.g. extractvalue indices)
          inserts     = [(after Inst, template CALL Inst, {arg index: ('c', i32) | ('v', old value id)})]: a copy of the
                        template call is inserted right after `after` (which must define a value); its value is insert j
          ref_edits   = [(Inst, flat op index of a 'rel' ref, j)]          the operand is pointed at inserted value j
        Value numbering is redone: new constants go after the old function constants, inserted values after their anchor."""
        first = self.first_inst
        cvals = sorted(set([v for _, _, v in const_edits] +
                           [x[1] for _, _, ov in inserts for x in ov.values() if x[0] == "c"]))
        k = len(cvals)
        cid = {v: first + j for j, v in enumerate(cvals)}
        if k:
            if self.fconsts is None:
                raise ValueError("no function constant block")
            i32 = self.m.i32_type()
            cb = self.fconsts
            last_type = None
            for r in recs(cb):
                if r.code == 1:
                    last_type = flat_ops(r)[0]

            def like(code, val):
                for r in recs(cb):
                    if r.code == code and r.abbrev is not None:
                        kinds = _abbrev_scalars(r.abbrev)
                        if len(kinds) == 1 and kinds[0][0] == "vbr":
                            return Rec(r.aid, r.abbrev, code, [r.ops[0], val])
                        if len(kinds) == 1 and kinds[0][0] == "fixed" and val < (1 << kinds[0][1]):
                            return Rec(r.aid, r.abbrev, code, [r.ops[0], val])
                return Rec(3, None, code, [val])
            if last_type != i32:
                cb.items.append(like(1, i32))
            for v in cvals:
                cb.items.append(like(4, _sv(v)))
        # inserted values: anchors sorted; old value v >= first moves by k + (number of inserts anchored before v)
        anchors = sorted(after.vid for after, _, _ in inserts)
        if any(a is None for a in anchors):
            raise ValueError("insert anchor defines no value")
        import bisect

        def nv(v):
            return v if v < first else v + k + bisect.bisect_left(anchors, v)

        def ninum(inum):
            return inum + k + bisect.bisect_left(anchors, inum)
        ins_id = {}
        rank = collections.Counter()
        order = sorted(range(len(inserts)), key=lambda j: inserts[j][0].vid)
        for j in order:
            a = inserts[j][0].vid
            ins_id[j] = nv(a) + 1 + rank[a]
            rank[a] += 1
        cedit = {(id(it), oi): v for it, oi, v in const_edits}
        redit = {(id(it), oi): j for it, oi, j in ref_edits}
        ledit = collections.defaultdict(list)
        for it, oi, v in lit_edits:
            ledit[id(it)].append((oi, v))
        for it in self.insts:
            ops = list(it.ops)
            inum, new_inum = it.num, ninum(it.num)
            for oi, kind in it.refs:
                if kind == "abs":
                    ops[oi] = nv(ops[oi])
                    continue
                if kind == "relsigned":
                    raw = ops[oi]
                    rel = -(raw >> 1) if raw & 1 else raw >> 1
                    rel = new_inum - nv(inum - rel)
                    ops[oi] = ((-rel) << 1) | 1 if rel < 0 else rel << 1
                    continue
                if (id(it), oi) in redit:
                    tgt = ins_id[redit[(id(it), oi)]]
                elif (id(it), oi) in cedit:
                    tgt = cid[cedit[(id(it), oi)]]
                else:
                    tgt = nv(inum - ops[oi])
                ops[oi] = new_inum - tgt
            for oi, v in ledit.get(id(it), ()):
                ops[oi] = v
            if ops != it.ops:
                set_flat(it.rec, ops)
        # inserted records
        by_anchor = collections.defaultdict(list)
        for j in order:
            by_anchor[id(inserts[j][0].rec)].append(j)
        for j in order:
            after, tpl, ov = inserts[j]
            fnid, args, consts, a0 = tpl.call
            me = ins_id[j]
            ops = list(tpl.ops)
            ops[a0 - 1] = me - fnid                              # callee (a module-level function: unchanged id)
            for ai, old in enumerate(args):
                if ai in ov:
                    kind, val = ov[ai]
                    tgt = cid[val] if kind == "c" else nv(val)
                else:
                    tgt = nv(old)
                ops[a0 + ai] = me - tgt
            rec = Rec(tpl.rec.aid, tpl.rec.abbrev, tpl.rec.code, list(tpl.rec.ops))
            set_flat(rec, ops)
            tpl_rec = rec
            items = self.fb.items
            pos = next(i for i, x in enumerate(items) if x is after.rec)
            n_before = by_anchor[id(after.rec)].index(j)
            items.insert(pos + 1 + n_before, tpl_rec)
        if inserts:
            # METADATA_ATTACHMENT (block 16) records [instruction ordinal, (kind, node)...]: ordinals of the instructions
            # after an inserted one move up (ordinal = position among the function's instruction records)
            ordn, n_ = {}, 0
            for it in self.insts:
                if it.code not in (1, 33, 35):       # DECLAREBLOCKS / DEBUG_LOC_AGAIN / DEBUG_LOC are no instructions
                    ordn[id(it)] = n_
                    n_ += 1
            ins_ord = sorted(ordn[id(after)] for after, _, _ in inserts)
            for mab in sub(self.fb, 16):
                for r in recs(mab):
                    ops = flat_ops(r)
                    if r.code == 11 and len(ops) % 2 == 1:
                        ops[0] = ops[0] + bisect.bisect_left(ins_ord, ops[0])
                        set_flat(r, ops)
        if k or inserts:
            for vst in sub(self.fb, 14):        # function VST: absolute value ids
                for r in recs(vst):
                    ops = flat_ops(r)
                    if r.code == 1 and ops:
                        ops[0] = nv(ops[0])
                        set_flat(r, ops)
        return emit(self.top)


def _sv(v):
    """LLVM signed VBR value encoding"""
    return v << 1 if v >= 0 else ((-v) << 1) | 1


def retarget(bitcode, edits_fn):
    """edits_fn(call_records) -> [(call index, arg index, new value)]; call_records = [(index, fn value id, [arg ValNos], [const values or None], value id)].
    Returns new bitcode bytes, None when there is nothing to change.  (p1_shader_fix; see Program for general edits)"""
    p = Program(bitcode)
    calls = p.calls()
    edits = edits_fn([(ci, it.call[0], it.call[1], it.call[2], it.vid) for ci, it in enumerate(calls)])
    if not edits:
        return None
    return p.emit([(calls[ci], calls[ci].call[3] + ai, v) for ci, ai, v in edits])


def selftest(bitcode):
    return emit(parse(bitcode)) == bitcode
