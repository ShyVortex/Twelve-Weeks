"""Tiny GAS -> flat-code linker for the winmm code caves (used by slots8.py).

Assembles GNU-as Intel-syntax text (the mingw `as` from tools/win/ext/msys64) into a COFF object, then applies the relocations
itself against a symbol table the caller supplies, so the caves need no real link step (ld cannot resolve rel32 branches into
the 0x18xxxxxxx image from an object in a different VA range). Symbols the assembly may reference but not define:

  V_<hex>   an absolute virtual address (engine code / data), e.g. `call V_180050fd0`, `lea rax, [rip + V_180135388]`
  D_<name>  an address from the caller's data table
  anything else: a label defined in any chunk of the same Cave

All relocations are 32-bit pc-relative (REL32, REL32_1..5) or ADDR32/ADDR64 (never emitted: cave code is position independent
apart from the rel32 it patches in, so it never needs the .reloc table).
"""
import os
import struct
import subprocess
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

AS = None


def _as_exe():
    global AS
    if AS is None:
        here = os.path.dirname(os.path.abspath(__file__))
        tools = os.path.dirname(here)
        cand = [os.path.join(tools, "win", "ext", "msys64", "ucrt64", "bin", "as.exe"),
                os.path.join(tools, "..", "..", "..", "tools", "win", "ext", "msys64", "ucrt64", "bin", "as.exe")]
        # a git worktree has no tools/win (untracked): search up for the main checkout's copy
        d = here
        for _ in range(8):
            d = os.path.dirname(d)
            cand.append(os.path.join(d, "tools", "win", "ext", "msys64", "ucrt64", "bin", "as.exe"))
        for c in cand:
            if os.path.exists(c):
                AS = os.path.abspath(c)
                break
        else:
            raise SystemExit("cave_link: no mingw as.exe found (tools/win/ext/msys64/ucrt64/bin)")
    return AS


def assemble(text):
    """-> (code bytes of .text, {label: offset}, [(offset, type, symbol, addend_in_field)]) ; asserts one .text and nothing else with content."""
    exe = _as_exe()
    with tempfile.TemporaryDirectory(dir=os.environ.get("T2R_TMP", None)) as td:
        src = os.path.join(td, "c.S")
        obj = os.path.join(td, "c.o")
        with open(src, "w") as f:
            f.write(".intel_syntax noprefix\n.text\n" + text + "\n")
        r = subprocess.run([exe, "--64", "-o", obj, src], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("cave_link: as failed:\n" + r.stderr + "\n--- source ---\n" +
                             "\n".join(f"{i + 3:4d} {l}" for i, l in enumerate(text.splitlines())))
        o = open(obj, "rb").read()
    return parse_coff(o)


def parse_coff(o):
    machine, nsec, _, symptr, nsym, optsz, _ = struct.unpack_from("<HHIIIHH", o, 0)
    assert machine == 0x8664
    strtab = symptr + 18 * nsym
    syms = []
    i = 0
    while i < nsym:
        b = symptr + 18 * i
        name = o[b:b + 8]
        if name[:4] == b"\0\0\0\0":
            off = struct.unpack_from("<I", name, 4)[0]
            e = o.index(b"\0", strtab + off)
            nm = o[strtab + off:e].decode()
        else:
            nm = name.rstrip(b"\0").decode()
        val, sec, typ, cls, aux = struct.unpack_from("<IhHBB", o, b + 8)
        syms.append((nm, val, sec, cls))
        syms.extend([None] * aux)
        i += 1 + aux
    text = None
    for s in range(nsec):
        b = 20 + optsz + 40 * s
        nm = o[b:b + 8].rstrip(b"\0").decode()
        vsz, vaddr, rawsz, rawptr, relptr, _, nrel, _, chars = struct.unpack_from("<IIIIIIHHI", o, b + 8)
        if nm == ".text":
            code = o[rawptr:rawptr + rawsz]
            rels = []
            for k in range(nrel):
                ro = relptr + 10 * k
                va, si, tp = struct.unpack_from("<IIH", o, ro)
                rels.append((va, tp, syms[si][0], struct.unpack_from("<i", code, va)[0]))
            text = (code, rels, s + 1)
        elif rawsz and nm not in (".data", ".bss", ".text") and not nm.startswith(".drectve") and not nm.startswith(".note"):
            pass
    assert text is not None, "no .text"
    code, rels, secno = text
    labels = {}
    for sym in syms:
        if sym and sym[2] == secno and sym[3] in (2, 3, 6) and not sym[0].startswith(".") and not sym[0].startswith("L"):
            labels[sym[0]] = sym[1]
    return code, labels, rels


class Cave:
    """Flat code image placed at `base` (a virtual address, image base included). add() appends a chunk, link(syms) resolves."""

    def __init__(self, base):
        self.base = base
        self.code = bytearray()
        self.labels = {}                    # name -> absolute VA
        self.relocs = []                    # (absolute offset into code, type, symbol, addend)
        self.tags = []                      # (offset, length, name) for the report

    def align(self, n=16, fill=0xcc):
        while len(self.code) % n:
            self.code.append(fill)

    def add(self, text, name=None):
        self.align(16)
        code, labels, rels = assemble(text)
        off = len(self.code)
        for l, v in labels.items():
            if l in self.labels:
                raise SystemExit(f"cave_link: duplicate label {l}")
            self.labels[l] = self.base + off + v
        for va, tp, sym, add in rels:
            self.relocs.append((off + va, tp, sym, add))
        self.code += code
        self.tags.append((off, len(code), name or "chunk"))
        return off

    def label_va(self, name):
        return self.labels[name]

    def resolve(self, sym, data):
        if sym.startswith("V_"):
            return int(sym[2:], 16)
        if sym.startswith("D_"):
            return data[sym[2:]]
        if sym in self.labels:
            return self.labels[sym]
        raise SystemExit(f"cave_link: undefined symbol {sym}")

    def link(self, data=None):
        data = data or {}
        out = bytearray(self.code)
        for off, tp, sym, add in self.relocs:
            tgt = self.resolve(sym, data)
            if tp == 4:                                 # REL32: relative to the end of the 4-byte field
                v = tgt - (self.base + off + 4) + add
            elif 5 <= tp <= 9:                          # REL32_1..5: end of field + n (immediate bytes still to come)
                v = tgt - (self.base + off + 4 + (tp - 4)) + add
            elif tp == 2:                               # ADDR32 (image-base relative would be 3; neither is expected)
                raise SystemExit(f"cave_link: absolute reloc against {sym} (use [rip + sym])")
            else:
                raise SystemExit(f"cave_link: unsupported relocation type {tp} against {sym}")
            if not -(1 << 31) <= v < (1 << 31):
                raise SystemExit(f"cave_link: rel32 to {sym} out of range")
            struct.pack_into("<i", out, off, v)
        return bytes(out)
