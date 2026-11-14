"""winmm cave: map the Part I side file BEHIND the mod blob (T2R_P1_SIDE_VIRT, re/part1/side-files.md "Plan").

The engine reads the mod archive through winmm's chunk hook 0x180002e10, which copies from `[0x1801398d0] + (req.offset - [0x1801398e8])` after
checking `offset + count <= [0x1801398d8]`; winmm's directory pass (0x180002479) aborts the WHOLE mod mount when one directory entry ends past
`[0x1801398d8]`. t2r_pack.split_payload cuts the encrypted archive at T = size1 (the T2ME payload, whose bytes stay in the DLL) so that
(file offset of the payload + T) % 64 KiB == 0; the rest (size2 bytes) is the side file `t2r-maps\\part1\\part1.dat` next to winmm.dll.

This module appends a section `.t2rps` (RWX) and patches the loader (0x180001180) right after its FNV check (0x180001999 cmp, 0x1800019a0 jne):
the `jne fail` is replaced by `jmp cave`; the cave re-does the `jne`, then

  1. resolves CreateFileMappingW / MapViewOfFileEx / UnmapViewOfFile (GetProcAddress on kernel32), opens winmm.dll and the side file,
  2. reserves size1' + size2' of address space, releases it and maps  view1 = winmm.dll [floor64K(FO) .. +delta+size1)  and
     view2 = the side file  contiguously (retrying with a fresh address up to 8 times: another thread may take the hole),
  3. sets `[0x1801398d0] = view1 + delta`, `[0x1801398d8] = size1 + size2`  (status MAPPED).
  FAIL SAFE: side file absent (status ABSENT), wrong size or any API / mapping failure (status FAILED + step + GetLastError): the same globals
  are set with view2 only RESERVED (view1 is still mapped, so the directory pass passes and the mod mounts; any read into the hole faults, but the
  ext's guard keeps every Part I map unselectable). If even view1 cannot be mapped, `[d0]` stays the blob in the image and only `[d8]` grows
  (layout 2: the mount passes, Part I reads would run past the blob).
  FO = `[0x1801398e8]` (the payload's FILE offset), taken at run time, so a shrink_rsrc / section move needs no rebuild: only (delta + T) % 64 KiB == 0
  must hold, which the build asserts on the finished DLL.

The section starts with a descriptor the ext reads (find the section by name `.t2rps`):
  +0x00 u32 'P1SD'  +0x04 u32 version 1  +0x08 u32 status (0 = not run, 1 mapped, 2 absent, 3 failed)  +0x0C u32 layout (0 none, 1 view1 + reserved
  hole, 2 blob in image / size extended, 3 full map)  +0x10 u32 step of the failure  +0x14 u32 GetLastError / 0xFFFF000n internal code
  +0x18 u64 size1  +0x20 u64 size2 (baked)  +0x28 u64 view base  +0x30 u64 payload pointer set  +0x38 u64 delta  +0x40 u64 actual side file size
  +0x60 u64 size2 (config, read by the cave)  +0x68 16 bytes build id (config)
The side file = the cut-off encrypted DSAR tail (size2 bytes) + a 16-byte trailer = the build id (first 16 bytes of sha256 of the T2ME payload).
Steps: 1 API resolve, 2 module path, 3 open winmm.dll, 4 map winmm.dll, 5 open side file, 6 side size, 7 map side file, 8 reserve / map views, 9 geometry.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cave_link  # noqa: E402

IMAGE_BASE = 0x180000000
NAME = b".t2rps"
HOOK_VMA = 0x1800019A0                       # jne 0x180001adb (6 bytes) after cmp r8,[0x1801398e0]
HOOK_ORIG = bytes.fromhex("0f85") + struct.pack("<i", 0x180001ADB - (0x1800019A0 + 6))
SIDE_FILE = "t2r-maps\\part1\\part1.dat"
MAGIC = 0x44533150                           # 'P1SD'

OFF_STATUS, OFF_LAYOUT, OFF_STEP, OFF_ERR = 0x08, 0x0C, 0x10, 0x14
OFF_SIZE1, OFF_SIZE2, OFF_BASE, OFF_PTR, OFF_DELTA, OFF_ACTUAL = 0x18, 0x20, 0x28, 0x30, 0x38, 0x40
OFF_CFG_SIZE2 = 0x60
OFF_CFG_ID = 0x68                             # 16 bytes: the build id the side file's trailer must carry
OFF_PCFM, OFF_PMVF, OFF_PUMV = 0x80, 0x88, 0x90
OFF_STR_K32, OFF_N_CFM, OFF_N_MVF, OFF_N_UMV, OFF_STR_SIDE = 0x100, 0x140, 0x160, 0x180, 0x200
CODE_OFF = 0x400

# IAT slots of the unpatched winmm the cave calls through (checked against the imports by tools/tests/test_p1_side_map.py)
IAT = {"CreateFileW": 0x180129520, "CloseHandle": 0x180129508, "GetFileSizeEx": 0x180129648, "GetLastError": 0x180129658,
       "GetModuleFileNameW": 0x180129668, "GetModuleHandleW": 0x180129680, "GetProcAddress": 0x180129690,
       "VirtualAlloc": 0x1801298B8, "VirtualFree": 0x1801298C0}
G_D0, G_D8, G_E8 = 0x1801398D0, 0x1801398D8, 0x1801398E8

ASM = r"""
.globl p1s_entry
p1s_entry:
    jne     V_180001adb                         # the loader's own failure branch (flags are the loader's cmp)
    sub     rsp, 0x520
    mov     qword ptr [rsp + 0x50], 0           # hDll
    mov     qword ptr [rsp + 0x58], 0           # hSide
    mov     qword ptr [rsp + 0x60], 0           # mapDll
    mov     qword ptr [rsp + 0x68], 0           # mapSide
    mov     qword ptr [rsp + 0xA8], 0           # view1
    mov     qword ptr [rsp + 0xB0], 0           # view2
    mov     rax, qword ptr [rip + V_1801398d8]
    mov     qword ptr [rsp + 0x70], rax         # size1
    mov     qword ptr [rip + D_size1], rax
    mov     rax, qword ptr [rip + V_1801398e8]
    mov     qword ptr [rsp + 0x80], rax         # FO
    mov     rax, qword ptr [rip + D_cfg_size2]
    mov     qword ptr [rsp + 0x78], rax         # size2
    mov     qword ptr [rip + D_size2], rax
    test    rax, rax
    jz      p1s_done                            # no side data baked: nothing to do (status stays 0)
    mov     dword ptr [rip + D_status], 3       # FAILED until proven otherwise
    mov     rax, qword ptr [rsp + 0x80]
    and     eax, 0xffff
    mov     qword ptr [rsp + 0x88], rax         # delta
    mov     qword ptr [rip + D_delta], rax
    add     rax, qword ptr [rsp + 0x70]
    mov     qword ptr [rsp + 0x90], rax         # view1_len = delta + size1
    mov     rax, qword ptr [rsp + 0x78]
    add     rax, 16 + 0xffff                    # the side file is size2 + a 16-byte build-id trailer
    and     rax, -0x10000
    add     rax, qword ptr [rsp + 0x90]
    mov     qword ptr [rsp + 0x98], rax         # total reservation (view1 + 64K-rounded side)
    test    dword ptr [rsp + 0x90], 0xffff
    jnz     p1s_geom
    # --- 1. APIs
    lea     rcx, [rip + D_str_k32]
    call    qword ptr [rip + V_180129680]       # GetModuleHandleW
    test    rax, rax
    jz      p1s_f_api
    mov     qword ptr [rsp + 0xD8], rax
    mov     rcx, rax
    lea     rdx, [rip + D_n_cfm]
    call    qword ptr [rip + V_180129690]       # GetProcAddress
    test    rax, rax
    jz      p1s_f_api
    mov     qword ptr [rip + D_pcfm], rax
    mov     rcx, qword ptr [rsp + 0xD8]
    lea     rdx, [rip + D_n_mvf]
    call    qword ptr [rip + V_180129690]
    test    rax, rax
    jz      p1s_f_api
    mov     qword ptr [rip + D_pmvf], rax
    mov     rcx, qword ptr [rsp + 0xD8]
    lea     rdx, [rip + D_n_umv]
    call    qword ptr [rip + V_180129690]
    test    rax, rax
    jz      p1s_f_api
    mov     qword ptr [rip + D_pumv], rax
    # --- 2. winmm.dll path
    lea     rcx, [rip + V_180000000]
    lea     rdx, [rsp + 0xE0]
    mov     r8d, 520
    call    qword ptr [rip + V_180129668]       # GetModuleFileNameW
    test    eax, eax
    jz      p1s_f_path
    cmp     eax, 470
    jae     p1s_f_path
    mov     qword ptr [rsp + 0xC8], rax         # length in wchars
    lea     rcx, [rsp + 0xE0]
    mov     edx, 0x80000000
    mov     r8d, 7
    xor     r9d, r9d
    mov     qword ptr [rsp + 0x20], 3
    mov     qword ptr [rsp + 0x28], 0x80
    mov     qword ptr [rsp + 0x30], 0
    call    qword ptr [rip + V_180129520]       # CreateFileW(winmm.dll)
    cmp     rax, -1
    je      p1s_f_dll
    mov     qword ptr [rsp + 0x50], rax
    mov     rcx, rax
    xor     edx, edx
    mov     r8d, 2                              # PAGE_READONLY
    xor     r9d, r9d
    mov     qword ptr [rsp + 0x20], 0
    mov     qword ptr [rsp + 0x28], 0
    call    qword ptr [rip + D_pcfm]
    test    rax, rax
    jz      p1s_f_mapdll
    mov     qword ptr [rsp + 0x60], rax
    # --- 3. side file path = <dir of winmm.dll>\t2r-maps\part1\part1.dat
    mov     r11, qword ptr [rsp + 0xC8]
p1s_scan:
    test    r11, r11
    jz      p1s_f_path
    dec     r11
    cmp     word ptr [rsp + r11*2 + 0xE0], 0x5c
    jne     p1s_scan
    inc     r11
    lea     rdx, [rip + D_str_side]
    lea     rcx, [rsp + r11*2 + 0xE0]
p1s_cp:
    movzx   eax, word ptr [rdx]
    mov     word ptr [rcx], ax
    add     rdx, 2
    add     rcx, 2
    test    eax, eax
    jnz     p1s_cp
    lea     rcx, [rsp + 0xE0]
    mov     edx, 0x80000000
    mov     r8d, 7
    xor     r9d, r9d
    mov     qword ptr [rsp + 0x20], 3
    mov     qword ptr [rsp + 0x28], 0x80
    mov     qword ptr [rsp + 0x30], 0
    call    qword ptr [rip + V_180129520]       # CreateFileW(part1.dat)
    cmp     rax, -1
    jne     p1s_side_open
    call    qword ptr [rip + V_180129658]       # GetLastError
    mov     dword ptr [rip + D_err], eax
    cmp     eax, 2
    je      p1s_absent
    cmp     eax, 3
    je      p1s_absent
    mov     dword ptr [rip + D_step], 5
    jmp     p1s_fallback
p1s_side_open:
    mov     qword ptr [rsp + 0x58], rax
    mov     rcx, rax
    lea     rdx, [rsp + 0xD0]
    call    qword ptr [rip + V_180129648]       # GetFileSizeEx
    test    eax, eax
    jz      p1s_f_size
    mov     rax, qword ptr [rsp + 0xD0]
    mov     qword ptr [rip + D_actual], rax
    sub     rax, 16
    cmp     rax, qword ptr [rsp + 0x78]
    jne     p1s_f_size2
    mov     rcx, qword ptr [rsp + 0x58]
    xor     edx, edx
    mov     r8d, 2
    xor     r9d, r9d
    mov     qword ptr [rsp + 0x20], 0
    mov     qword ptr [rsp + 0x28], 0
    call    qword ptr [rip + D_pcfm]
    test    rax, rax
    jz      p1s_f_mapside
    mov     qword ptr [rsp + 0x68], rax
    # --- 4. contiguous views: reserve, release, map both at the hole (retry on a lost race)
    mov     qword ptr [rsp + 0xC8], 8
p1s_try:
    xor     ecx, ecx
    mov     rdx, qword ptr [rsp + 0x98]
    mov     r8d, 0x2000                         # MEM_RESERVE
    mov     r9d, 1                              # PAGE_NOACCESS
    call    qword ptr [rip + V_1801298b8]
    test    rax, rax
    jz      p1s_f_reserve
    mov     qword ptr [rsp + 0xA0], rax
    mov     rcx, rax
    xor     edx, edx
    mov     r8d, 0x8000                         # MEM_RELEASE
    call    qword ptr [rip + V_1801298c0]
    mov     rax, qword ptr [rsp + 0x80]
    sub     rax, qword ptr [rsp + 0x88]         # floor64K(FO)
    mov     r9d, eax
    mov     r8, rax
    shr     r8, 32
    mov     rcx, qword ptr [rsp + 0x60]
    mov     edx, 4                              # FILE_MAP_READ
    mov     rax, qword ptr [rsp + 0x90]
    mov     qword ptr [rsp + 0x20], rax
    mov     rax, qword ptr [rsp + 0xA0]
    mov     qword ptr [rsp + 0x28], rax
    call    qword ptr [rip + D_pmvf]
    test    rax, rax
    jz      p1s_retry
    mov     qword ptr [rsp + 0xA8], rax
    mov     rcx, qword ptr [rsp + 0x68]
    mov     edx, 4
    xor     r8d, r8d
    xor     r9d, r9d
    mov     qword ptr [rsp + 0x20], 0
    mov     rax, qword ptr [rsp + 0xA0]
    add     rax, qword ptr [rsp + 0x90]
    mov     qword ptr [rsp + 0x28], rax
    call    qword ptr [rip + D_pmvf]
    test    rax, rax
    jnz     p1s_mapped
    mov     rcx, qword ptr [rsp + 0xA8]
    call    qword ptr [rip + D_pumv]
    mov     qword ptr [rsp + 0xA8], 0
p1s_retry:
    dec     qword ptr [rsp + 0xC8]
    jnz     p1s_try
    mov     dword ptr [rip + D_step], 8
    call    qword ptr [rip + V_180129658]
    mov     dword ptr [rip + D_err], eax
    jmp     p1s_fallback
p1s_mapped:
    mov     qword ptr [rsp + 0xB0], rax
    mov     rcx, rax
    add     rcx, qword ptr [rsp + 0x78]         # the trailer behind the side data: must be this blob's build id
    mov     rdx, qword ptr [rip + D_cfg_id]
    cmp     rdx, qword ptr [rcx]
    jne     p1s_idbad
    mov     rdx, qword ptr [rip + D_cfg_id + 8]
    cmp     rdx, qword ptr [rcx + 8]
    jne     p1s_idbad
    mov     rax, qword ptr [rsp + 0xB0]
    mov     rax, qword ptr [rsp + 0xA8]
    mov     qword ptr [rip + D_base], rax
    add     rax, qword ptr [rsp + 0x88]
    mov     qword ptr [rip + V_1801398d0], rax
    mov     qword ptr [rip + D_ptr], rax
    mov     rax, qword ptr [rsp + 0x70]
    add     rax, qword ptr [rsp + 0x78]
    mov     qword ptr [rip + V_1801398d8], rax
    mov     dword ptr [rip + D_layout], 3
    mov     dword ptr [rip + D_status], 1
    jmp     p1s_done

# --- failure exits: record the step, then the reserved-only layout
p1s_idbad:
    mov     rcx, qword ptr [rsp + 0xB0]
    call    qword ptr [rip + D_pumv]            # another build's part1.dat: drop both views, reserved-only layout
    mov     rcx, qword ptr [rsp + 0xA8]
    call    qword ptr [rip + D_pumv]
    mov     qword ptr [rsp + 0xB0], 0
    mov     qword ptr [rsp + 0xA8], 0
    mov     dword ptr [rip + D_step], 7
    mov     dword ptr [rip + D_err], 0xffff0004
    jmp     p1s_fallback
p1s_geom:
    mov     dword ptr [rip + D_step], 9
    mov     dword ptr [rip + D_err], 0xffff0002
    jmp     p1s_fallback
p1s_f_api:
    mov     dword ptr [rip + D_step], 1
    jmp     p1s_lasterr
p1s_f_path:
    mov     dword ptr [rip + D_step], 2
    jmp     p1s_lasterr
p1s_f_dll:
    mov     dword ptr [rip + D_step], 3
    jmp     p1s_lasterr
p1s_f_mapdll:
    mov     dword ptr [rip + D_step], 4
    jmp     p1s_lasterr
p1s_f_size:
    mov     dword ptr [rip + D_step], 6
    jmp     p1s_lasterr
p1s_f_size2:
    mov     dword ptr [rip + D_step], 6
    mov     dword ptr [rip + D_err], 0xffff0003
    jmp     p1s_fallback
p1s_f_mapside:
    mov     dword ptr [rip + D_step], 7
    jmp     p1s_lasterr
p1s_f_reserve:
    mov     dword ptr [rip + D_step], 8
p1s_lasterr:
    call    qword ptr [rip + V_180129658]
    mov     dword ptr [rip + D_err], eax
    jmp     p1s_fallback
p1s_absent:
    mov     dword ptr [rip + D_status], 2
p1s_fallback:
    # reserved-only: [view1 | hole].  Needs the DLL mapping; without it the blob in the image stays and only the size grows (layout 2).
    mov     rax, qword ptr [rsp + 0x70]
    add     rax, qword ptr [rsp + 0x78]
    mov     qword ptr [rsp + 0xB8], rax         # new d8
    cmp     qword ptr [rsp + 0x60], 0
    je      p1s_last
    mov     qword ptr [rsp + 0xC8], 8
p1s_ftry:
    xor     ecx, ecx
    mov     rdx, qword ptr [rsp + 0x98]
    mov     r8d, 0x2000
    mov     r9d, 1
    call    qword ptr [rip + V_1801298b8]
    test    rax, rax
    jz      p1s_last
    mov     qword ptr [rsp + 0xA0], rax
    mov     rcx, rax
    xor     edx, edx
    mov     r8d, 0x8000
    call    qword ptr [rip + V_1801298c0]
    mov     rax, qword ptr [rsp + 0x80]
    sub     rax, qword ptr [rsp + 0x88]
    mov     r9d, eax
    mov     r8, rax
    shr     r8, 32
    mov     rcx, qword ptr [rsp + 0x60]
    mov     edx, 4
    mov     rax, qword ptr [rsp + 0x90]
    mov     qword ptr [rsp + 0x20], rax
    mov     rax, qword ptr [rsp + 0xA0]
    mov     qword ptr [rsp + 0x28], rax
    call    qword ptr [rip + D_pmvf]
    test    rax, rax
    jz      p1s_fretry
    mov     qword ptr [rsp + 0xA8], rax
    # reserve the hole behind view1 so nothing else lands there
    mov     rcx, qword ptr [rsp + 0xA8]
    add     rcx, qword ptr [rsp + 0x90]
    mov     rdx, qword ptr [rsp + 0x98]
    sub     rdx, qword ptr [rsp + 0x90]
    mov     r8d, 0x2000
    mov     r9d, 1
    call    qword ptr [rip + V_1801298b8]
    test    rax, rax
    jnz     p1s_have1
    mov     rcx, qword ptr [rsp + 0xA8]
    call    qword ptr [rip + D_pumv]
    mov     qword ptr [rsp + 0xA8], 0
p1s_fretry:
    dec     qword ptr [rsp + 0xC8]
    jnz     p1s_ftry
    jmp     p1s_last
p1s_have1:
    mov     rax, qword ptr [rsp + 0xA8]
    mov     qword ptr [rip + D_base], rax
    add     rax, qword ptr [rsp + 0x88]
    mov     qword ptr [rip + V_1801398d0], rax
    mov     qword ptr [rip + D_ptr], rax
    mov     rax, qword ptr [rsp + 0xB8]
    mov     qword ptr [rip + V_1801398d8], rax
    mov     dword ptr [rip + D_layout], 1
    jmp     p1s_done
p1s_last:
    mov     rax, qword ptr [rsp + 0xB8]
    mov     qword ptr [rip + V_1801398d8], rax
    mov     dword ptr [rip + D_layout], 2
p1s_done:
    mov     rcx, qword ptr [rsp + 0x50]
    test    rcx, rcx
    jz      p1s_c1
    call    qword ptr [rip + V_180129508]
p1s_c1:
    mov     rcx, qword ptr [rsp + 0x58]
    test    rcx, rcx
    jz      p1s_c2
    call    qword ptr [rip + V_180129508]
p1s_c2:
    mov     rcx, qword ptr [rsp + 0x60]
    test    rcx, rcx
    jz      p1s_c3
    call    qword ptr [rip + V_180129508]
p1s_c3:
    mov     rcx, qword ptr [rsp + 0x68]
    test    rcx, rcx
    jz      p1s_c4
    call    qword ptr [rip + V_180129508]
p1s_c4:
    add     rsp, 0x520
    jmp     V_1800019a6
"""


def build_section(sec_va, size2, build_id=bytes(16)):
    """-> (section bytes: descriptor/data + linked code, entry VA, labels)"""
    base = IMAGE_BASE + sec_va
    cave = cave_link.Cave(base + CODE_OFF)
    cave.add(ASM, "p1s")
    data = {n: base + o for n, o in {
        "status": OFF_STATUS, "layout": OFF_LAYOUT, "step": OFF_STEP, "err": OFF_ERR, "size1": OFF_SIZE1, "size2": OFF_SIZE2,
        "base": OFF_BASE, "ptr": OFF_PTR, "delta": OFF_DELTA, "actual": OFF_ACTUAL, "cfg_size2": OFF_CFG_SIZE2, "cfg_id": OFF_CFG_ID,
        "pcfm": OFF_PCFM, "pmvf": OFF_PMVF, "pumv": OFF_PUMV, "str_k32": OFF_STR_K32, "n_cfm": OFF_N_CFM, "n_mvf": OFF_N_MVF,
        "n_umv": OFF_N_UMV, "str_side": OFF_STR_SIDE}.items()}
    code = cave.link(data)
    sec = bytearray(CODE_OFF + len(code))
    struct.pack_into("<II", sec, 0, MAGIC, 1)
    struct.pack_into("<Q", sec, OFF_CFG_SIZE2, size2)
    assert len(build_id) == 16
    sec[OFF_CFG_ID:OFF_CFG_ID + 16] = build_id
    sec[OFF_STR_K32:OFF_STR_K32 + 26] = "kernel32.dll".encode("utf-16-le")
    for off, nm in ((OFF_N_CFM, b"CreateFileMappingW"), (OFF_N_MVF, b"MapViewOfFileEx"), (OFF_N_UMV, b"UnmapViewOfFile")):
        sec[off:off + len(nm)] = nm
    sd = (SIDE_FILE + "\0").encode("utf-16-le")
    assert OFF_STR_SIDE + len(sd) <= CODE_OFF
    sec[OFF_STR_SIDE:OFF_STR_SIDE + len(sd)] = sd
    sec[CODE_OFF:] = code
    return bytes(sec), cave.label_va("p1s_entry"), cave.labels


def add(data, size2, build_id=bytes(16)):
    """append `.t2rps` (RWX) with the cave and patch the loader's jne; -> new image bytes. Refuses on any unexpected original byte."""
    d = bytearray(data)
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[pe:pe + 4] == b"PE\0\0"
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    soi = struct.unpack_from("<I", d, opt + 56)[0]
    soh = struct.unpack_from("<I", d, opt + 60)[0]
    sa = struct.unpack_from("<I", d, opt + 32)[0]
    fa = struct.unpack_from("<I", d, opt + 36)[0]
    tab = opt + optsz
    secs = []
    for i in range(nsec):
        b = tab + 40 * i
        nm = bytes(d[b:b + 8]).rstrip(b"\0")
        vs, va, rs, rp = struct.unpack_from("<IIII", d, b + 8)
        if nm == NAME:
            raise SystemExit("p1 side map: section already present")
        secs.append((va, vs, rs, rp))

    def off_of(vma):
        rva = vma - IMAGE_BASE
        for va, vs, rs, rp in secs:
            if va <= rva < va + max(vs, rs):
                return rp + rva - va
        raise SystemExit(f"p1 side map: {vma:#x} not in a section")
    ho = off_of(HOOK_VMA)
    if bytes(d[ho:ho + 6]) != HOOK_ORIG:
        raise SystemExit(f"p1 side map: unexpected bytes at the loader hook {bytes(d[ho:ho + 6]).hex()}")
    so = tab + 40 * nsec
    if so + 40 > soh:
        raise SystemExit("p1 side map: no room for another section header")
    rva = (soi + sa - 1) // sa * sa
    sec, entry, _labels = build_section(rva, size2, build_id)
    raw_ptr = (len(d) + fa - 1) // fa * fa
    raw_size = (len(sec) + fa - 1) // fa * fa
    vsize = (len(sec) + sa - 1) // sa * sa
    d[so:so + 40] = struct.pack("<8sIIIIIIHHI", NAME, vsize, rva, raw_size, raw_ptr, 0, 0, 0, 0, 0xE0000060)   # CODE|INIT|EXEC|READ|WRITE
    struct.pack_into("<H", d, pe + 6, nsec + 1)
    struct.pack_into("<I", d, opt + 56, rva + vsize)
    d += b"\0" * (raw_ptr - len(d)) + sec + b"\0" * (raw_size - len(sec))
    rel = entry - (HOOK_VMA + 5)
    d[ho:ho + 6] = b"\xe9" + struct.pack("<i", rel) + b"\x90"
    return bytes(d)


def check(data):
    """build check: the section exists with the descriptor magic. -> section RVA"""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    tab = pe + 24 + optsz
    for i in range(nsec):
        b = tab + 40 * i
        if bytes(data[b:b + 8]).rstrip(b"\0") == NAME:
            vs, va, rs, rp = struct.unpack_from("<IIII", data, b + 8)
            if struct.unpack_from("<I", data, rp)[0] != MAGIC:
                raise SystemExit("p1 side map: descriptor magic missing")
            return va
    raise SystemExit("p1 side map: .t2rps missing")
