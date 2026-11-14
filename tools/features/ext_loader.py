"""Add the t2r-ext.dll loader to a T2R winmm.dll.

  python ext_loader.py <in.dll> <out.dll>

Appends an executable section '.t2rx' and hooks the entry of the per-frame match
function FUN_180063370 (runs on the game thread every frame) with a 5-byte JMP:

  cave:  sub rsp,28h
         if (!state) { state=1; h=LoadLibraryW(L"t2r-ext.dll");
                       if (h) tick=GetProcAddress(h,"t2r_tick"); }
         if (tick) tick();
         add rsp,28h
         push r15 / push r14 / push r13          ; displaced prologue (6 bytes)
         jmp 0x180063376

JMP-entered (never CALL-entered) so no return address points into the cave, which
has no unwind info (lesson from the old force-cave). Everything else lives in C in
t2r-ext.dll, next to the game exe.
"""
import struct
import sys

import pefile

IMAGE_BASE = 0x180000000
HOOK_VMA = 0x180063370
HOOK_ORIG = bytes.fromhex("41 57 41 56 41 55")      # push r15; push r14; push r13
RESUME_VMA = HOOK_VMA + len(HOOK_ORIG)
IAT_LOADLIBRARYW = 0x180129788
IAT_GETPROCADDRESS = 0x180129690


def build_cave(cave_va):
    data_off = 0x100                                    # data after code
    state_va = cave_va + data_off
    tick_va = state_va + 8
    dll_va = state_va + 0x10
    proc_va = dll_va + 0x40
    c = bytearray()

    def emit(prefix, target, suffix=b""):              # prefix + disp32(target) + suffix
        end = cave_va + len(c) + len(prefix) + 4 + len(suffix)
        c.extend(prefix + struct.pack("<i", target - end) + suffix)

    def jcc8(op):                                       # short conditional jump, target set by land()
        c.extend(bytes([op, 0]))
        return len(c) - 2

    def land(at):
        c[at + 1] = len(c) - (at + 2)

    c += b"\x48\x83\xec\x28"                            # sub rsp,0x28
    emit(b"\x80\x3d", state_va, b"\x00")                # cmp byte [state],0
    jne_have = jcc8(0x75)                               # jne have
    emit(b"\xc6\x05", state_va, b"\x01")                # mov byte [state],1
    emit(b"\x48\x8d\x0d", dll_va)                       # lea rcx,[dll]
    emit(b"\xff\x15", IAT_LOADLIBRARYW)                 # call [LoadLibraryW]
    c += b"\x48\x85\xc0"                                # test rax,rax
    jz_have = jcc8(0x74)                                # jz have
    c += b"\x48\x89\xc1"                                # mov rcx,rax
    emit(b"\x48\x8d\x15", proc_va)                      # lea rdx,[proc]
    emit(b"\xff\x15", IAT_GETPROCADDRESS)               # call [GetProcAddress]
    emit(b"\x48\x89\x05", tick_va)                      # mov [tick],rax
    land(jne_have)
    land(jz_have)
    emit(b"\x48\x8b\x05", tick_va)                      # mov rax,[tick]
    c += b"\x48\x85\xc0"                                # test rax,rax
    jz_done = jcc8(0x74)                                # jz done
    c += b"\xff\xd0"                                    # call rax
    land(jz_done)
    c += b"\x48\x83\xc4\x28"                            # add rsp,0x28
    c += HOOK_ORIG                                      # displaced prologue
    emit(b"\xe9", RESUME_VMA)                           # jmp back
    assert len(c) <= data_off
    c += b"\xcc" * (data_off - len(c))
    c += b"\0" * 0x10                                   # state, tick
    c += "t2r-ext.dll".encode("utf-16-le").ljust(0x40, b"\0")
    c += b"t2r_tick\0"
    return bytes(c)


def add_loader(data):
    pe = pefile.PE(data=data, fast_load=True)
    if any(s.Name.rstrip(b"\0") == b".t2rx" for s in pe.sections):
        raise SystemExit("loader already present")
    hook_off = pe.get_offset_from_rva(HOOK_VMA - IMAGE_BASE)
    if data[hook_off:hook_off + len(HOOK_ORIG)] != HOOK_ORIG:
        raise SystemExit("unexpected bytes at hook site")
    fa, sa = pe.OPTIONAL_HEADER.FileAlignment, pe.OPTIONAL_HEADER.SectionAlignment
    last = pe.sections[-1]
    rva = (last.VirtualAddress + last.Misc_VirtualSize + sa - 1) // sa * sa
    raw_ptr = (len(data) + fa - 1) // fa * fa
    cave = build_cave(IMAGE_BASE + rva)
    raw_size = (len(cave) + fa - 1) // fa * fa
    out = bytearray(data)
    sec_off = pe.DOS_HEADER.e_lfanew + 4 + 20 + pe.FILE_HEADER.SizeOfOptionalHeader \
        + 40 * pe.FILE_HEADER.NumberOfSections
    assert sec_off + 40 <= pe.OPTIONAL_HEADER.SizeOfHeaders
    out[sec_off:sec_off + 40] = struct.pack("<8sIIIIIIHHI", b".t2rx", len(cave), rva, raw_size,
                                            raw_ptr, 0, 0, 0, 0, 0xE0000020)  # CODE|EXEC|READ|WRITE
    struct.pack_into("<H", out, pe.DOS_HEADER.e_lfanew + 6, pe.FILE_HEADER.NumberOfSections + 1)
    struct.pack_into("<I", out, pe.OPTIONAL_HEADER.get_file_offset() + 56,
                     (rva + len(cave) + sa - 1) // sa * sa)               # SizeOfImage
    out += b"\0" * (raw_ptr - len(out)) + cave + b"\0" * (raw_size - len(cave))
    rel = (IMAGE_BASE + rva) - (HOOK_VMA + 5)
    out[hook_off:hook_off + 6] = b"\xe9" + struct.pack("<i", rel) + b"\x90"
    return bytes(out)


if __name__ == "__main__":
    src, dst = sys.argv[1:3]
    open(dst, "wb").write(add_loader(open(src, "rb").read()))
    print(f"{dst}: t2r-ext loader added")
