"""Part I -> TLOU2 shader ABI retarget (tools/part1/p1_abi.py, re/part1/geometry-upgrade.md s10).
Always: the committed reference layouts (tools/part1/data/p1_abi_ref.json) and the root-signature remap on a synthetic Part I
root signature.  With converted Bookstore paks (T2R_P1_CONV or <main>/re/part1/x/conv): the audit (no Part I global id left,
every root signature on TLOU2 offsets, every material with an EFFECT and all texture slots bound)."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "part1"))
import dxbc  # noqa: E402
import p1_abi  # noqa: E402

ref = p1_abi.Ref()
# ---- reference: every Part I global maps onto a TLOU2 one, parameter for parameter
assert ref.map == {0x3a89862b: 0x767c0614, 0x04a50665: 0x767c0614, 0x96c693b9: 0x6638bddc, 0xabb5ec8d: 0xbc7e24a6}, ref.map
for p1id, tid in ref.map.items():
    tn = {p["name"]: p for p in ref.t2[tid]["params"]}
    for p in ref.p1[p1id]["params"]:
        assert p["name"] in tn and tn[p["name"]]["size"] == p["size"] and tn[p["name"]]["sid"] == p["sid"], (hex(p1id), p["name"])
    if ref.role[tid] == "cbuffer":
        wm = ref.wmap[p1id]
        assert len(set(wm.values())) == len(wm), "word map not injective"
wm = ref.wmap[0x3a89862b]
assert wm[0x378 // 4] == 0x3a0 // 4 and wm[0x380 // 4] == 0x3a8 // 4     # g_flatNormals, g_time (the rows Part I shaders read most)
assert wm[0x10 // 4] == 0x10 // 4                                          # untouched head of the per-frame buffer
assert ref.wmap[0x96c693b9][0x870 // 4] == 0x8b0 // 4                      # g_occlusionParameters behind the inserted dummy
im = ref.imap[0xabb5ec8d]
assert im[0] == 0 and im[10] == 10 and im[13] == 15 and im[108] == 110 and im[145] == 147 and im[245] == 247
print("ok  reference layouts: %d Part I globals -> TLOU2 by name" % len(ref.map))

# ---- root signature: Part I global table (SRV x145 s4, x2 s201, x131 @147 s4, UAV x15 s4, appended) -> explicit TLOU2 offsets
A = dxbc.APPEND
rs = dxbc.RootSig.__new__(dxbc.RootSig)
rs.version, rs.flags, rs.samplers = 2, 0, []
rs.params = [[1, 0, [0, 0, 1]], [0, 0, [[2, A, 0, 2, 0, A]]],
             [0, 0, [[0, 145, 0, 4, 0, A], [0, 2, 0, 201, 0, A], [0, 131, 147, 4, 0, A], [1, 15, 0, 4, 0, A]]]]
raw = rs.encode()
c0 = bytearray(b"DXBC" + bytes(28))
struct.pack_into("<I", c0, 24, 32)
cont = dxbc.build(bytes(c0), [(b"RTS0", raw)])
new = dxbc.RootSig(dict(dxbc.parts(p1_abi.patch_rootsig(cont, im)))[b"RTS0"])
tab = {}
for r in new.params[2][2]:
    for j in range(r[1]):
        tab[("tu"[r[0]], r[3], r[2] + j)] = r[-1] + j
assert tab[("t", 4, 0)] == 0 and tab[("t", 4, 10)] == 10 and tab[("t", 4, 11)] == 13 and tab[("t", 4, 108)] == 110
assert tab[("t", 4, 144)] == 146 and tab[("t", 201, 0)] == 147 and tab[("t", 201, 1)] == 148 and tab[("t", 4, 147)] == 149
assert tab[("u", 4, 0)] == 280 and tab[("u", 4, 14)] == 294
assert new.params[:2] == rs.params[:2] and p1_abi._rts_ok(new, im) is None and p1_abi._rts_ok(rs, im) is not None
# Part I's sky signature leaves the s201 range out: its UAVs are appended 2 slots low (u0 at descriptor 276); they still have
# to land on TLOU2's u0 (280) - placement by register name, not by descriptor offset
rs.params[2][2] = [[0, 145, 0, 4, 0, A], [0, 131, 147, 4, 0, A], [1, 15, 0, 4, 0, A]]
cont = dxbc.build(bytes(c0), [(b"RTS0", rs.encode())])
new = dxbc.RootSig(dict(dxbc.parts(p1_abi.patch_rootsig(cont, im)))[b"RTS0"])
tab = {(("tu"[r[0]], r[3], r[2] + j)): r[-1] + j for r in new.params[2][2] for j in range(r[1])}
assert tab[("u", 4, 0)] == 280 and tab[("t", 4, 147)] == 149 and p1_abi._rts_ok(new, im) is None
print("ok  root signature remap: Part I registers on the TLOU2 offsets of the same names (also with a range left out)")

# ---- converted paks (optional)
main = os.path.dirname(TOOLS).split(os.sep + ".claude" + os.sep)[0]
# the shipped Part I set is the retargeted one (re/part1/geometry-upgrade.md s10: T2R_P1_CONV=<main>/re/part1/x/conv-abi); the old
# <main>/re/part1/x/conv is the pre-retarget conversion and fails this audit by design - it is only the fallback when conv-abi is missing
conv = os.environ.get("T2R_P1_CONV") or os.path.join(main, "re", "part1", "x", "conv-abi")
if not os.path.isdir(conv):
    conv = os.path.join(main, "re", "part1", "x", "conv")
paks = [os.path.join(conv, f) for f in sorted(os.listdir(conv))] if os.path.isdir(conv) else []
paks = [p for p in paks if p.endswith(".pak") and not p.endswith(("-phys.pak", "-ingame.pak")) and os.path.getsize(p) > 1_000_000]
if not paks:
    print("skip  converted-pak audit (no %s)" % conv)
    sys.exit(0)
for p in paks:
    bad, st, rows = p1_abi.check(p, ref, materials=True)
    assert not bad, (os.path.basename(p), bad[:3], "re-run: python tools/part1/p1_levelset.py convert <Part I dir> p1-bookstore --tex-drop=2")
    assert st["materials with problems"] == 0 and st["materials ok"] > 0, (os.path.basename(p), dict(st))
    print("ok  %s: %d materials, %d stages, root signatures %d on TLOU2 offsets" % (
        os.path.basename(p), st["materials ok"], st["stages"], st["root signatures on TLOU2 offsets"]))
