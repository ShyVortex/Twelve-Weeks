"""t2pak typed-item pages + trailer, snow_clone byte-identical round trip, EFFECT name-index schema, complete cross-pak material graft
(tools/part1/t2pak.py PageBuilder, tools/models/pak_graft.py, snow_clone.clone(donor_pak=...), pak_validate strict; re/mp-snow.md 8.19).
Needs the game's sp-common.psarc (stock actor paks via build_dll._game_pak, cached in re/gamebin/actor97); skips without it."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for d in ("models", "part1", "features"):
    sys.path.insert(0, os.path.join(TOOLS, d))
import t2pak  # noqa: E402
import snow_clone  # noqa: E402
import pak_graft  # noqa: E402
import pak_validate  # noqa: E402

try:
    import build_dll
    game = build_dll._game_pak
    game("militia-male-11-kit")
except Exception as e:      # noqa: BLE001
    print("skip: stock paks not readable (%s)" % str(e)[:80])
    sys.exit(0)

STOCK = ["militia-male-11-kit", "militia-male-07-kit", "scar-male-hooddown", "scar-male-a-jacket-kit", "ellie-patrol-jacket", "ellie-patrol-r-glove",
         "owen-tracking-body", "militia-male-a-legs-kit"]

# ---- round trip: an untouched pak serializes byte-identical (fixup-data offset align16(ft + 0x60), first page align16(end of fixups))
for n in STOCK:
    d = game(n)
    assert snow_clone.Pak(d).serialize() == d, n
    assert pak_validate.check(d, n) == [], (n, pak_validate.check(d, n)[:2])
print("ok  round trip + strict validator on %d stock paks" % len(STOCK))

# ---- PageBuilder: a new page with a typed VRAM_DESC item (copied from another pak, its stub appended to the trailer) + a new VRAM_DESC_TABLE
src = snow_clone.Pak(game("ellie-patrol-jacket"))
t = snow_clone.Pak(game("militia-male-11-kit"))
vd = next((pg, off) for ty, pg, off in src.items() if ty == "VRAM_DESC" and src.q(pg, off + 0x18) == 0x96109347aa619fa9)     # snow-color
size = src.u32(vd[0], vd[1] - 48 + 16)
pay = bytearray(src.pages[vd[0]][vd[1]:vd[1] + size])
doff, dsz = src.q(vd[0], vd[1] + 8), src.u32(vd[0], vd[1] + 0x10)
tl0 = len(t.trailer)
struct.pack_into("<Q", pay, 8, t.append_trailer(src.trailer[doff:doff + dsz]))
b = t2pak.PageBuilder(0)
loc = b.item("", "VRAM_DESC", bytes(pay))
b.ptr(loc + 0x48, ("L", loc + 0x50))
vt = pak_graft.vram_table(t)
vn = t.u32(*vt)
tab = bytearray(8 + 8 * (vn + 1))
struct.pack_into("<I", tab, 0, vn + 1)
vloc = b.item("", "VRAM_DESC_TABLE", bytes(tab))
for i in range(vn):
    b.ptr(vloc + 8 + 8 * i, t.ptr(vt[0], vt[1] + 8 + 8 * i))
b.ptr(vloc + 8 + 8 * vn, ("L", loc - 48))
t.drop_item(vt[0], vt[1] - 48)
(pg,) = t.commit([b])
t.vram_pg, t.vram_off = pg, b.loc(vloc) - 48
out = t.serialize()
r = snow_clone.Pak(out)
types = [ty for ty, p, o in r.items()]
assert types.count("VRAM_DESC_TABLE") == 1 and types.count("VRAM_DESC") == 118, (types.count("VRAM_DESC_TABLE"), types.count("VRAM_DESC"))
nv = next((p, o) for ty, p, o in r.items() if ty == "VRAM_DESC" and p == pg)
assert r.q(nv[0], nv[1] + 0x18) == 0x96109347aa619fa9 and snow_clone.cstr(r, *r.ptr(nv[0], nv[1] + 0x48)).endswith("snow-color.tga/2903960B941E4661.ndb")
assert r.trailer[r.q(nv[0], nv[1] + 8):][:dsz] == src.trailer[doff:doff + dsz] and r.q(nv[0], nv[1] + 8) >= tl0
assert (r.vram_pg, r.vram_off) == (pg, b.loc(vloc) - 48) and r.u32(pg, r.vram_off + 48) == vn + 1
import p1_convert  # noqa: E402
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as w:
    f = os.path.join(w, "x.pak")
    open(f, "wb").write(out)
    assert p1_convert.vram_check(f) == [] and p1_convert.vram_sort_check(f) == []
print("ok  PageBuilder: typed VRAM_DESC item + trailer stub + VRAM_DESC_TABLE replacement read back (t2pak, ndpak-style, p1 VRAM checks)")

# ---- EFFECT name-index schema: three kits predict each other byte for byte
import fx_index_proof  # noqa: E402
kits = [snow_clone.Pak(game(n)) for n in ("militia-male-11-kit", "militia-male-07-kit", "militia-male-a-legs-kit")]
h = 0x13acdf9cc8ca5980                                   # wlf-patch's effect
tot = [0, 0, 0]
for i in range(len(kits)):
    for j in range(len(kits)):
        if i != j and h in pak_graft.fx_table(kits[i])["entries"] and h in pak_graft.fx_table(kits[j])["entries"]:
            nf, nchg, resid = fx_index_proof.compare(kits[i], kits[j], h)
            tot = [tot[0] + nf, tot[1] + nchg, tot[2] + resid]
assert tot[0] > 1000 and tot[1] > 0 and tot[2] == 0, tot
print("ok  effect name indices: %d fields, %d differ between paks, 0 residual bytes" % (tot[0], tot[1]))

# ---- complete graft: Seraphite coat on Ellie's snow jacket, then the hands on her glove (second graft on the same pak)
recv = game("scar-male-a-jacket-kit")
rep = {}
d1 = snow_clone.clone(recv, "scar-m-coat-a", "jacket", rep, donor_pak=game("ellie-patrol-jacket"))
g = rep["graft"]
assert g["layouts added"] == 3 and g["textures added"] > 0 and g["index fields remapped"] > 500, g
assert pak_validate.check(d1, "coat") == [], pak_validate.check(d1, "coat")[:3]
d2 = snow_clone.clone(d1, "scar-m-hands", "gloves", {}, donor_pak=game("ellie-patrol-r-glove"))
assert pak_validate.check(d2, "hands") == [], pak_validate.check(d2, "hands")[:3]
t2 = snow_clone.Pak(d2)
assert snow_clone.Pak(d2).serialize() == d2
dj = snow_clone.Pak(game("ellie-patrol-jacket"))
rec = snow_clone.techniques(t2)["scar-m-coat-a"]
hcoat = t2.q(rec[0], rec[1] + 0x10)
nf, nchg, resid = fx_index_proof.compare(dj, t2, hcoat)
assert nf > 500 and resid == 0, (nf, resid)
# pool slice = the clone's params (the GPU reads the material constants there)
fx = pak_graft.fx_table(t2)
params, _ = snow_clone.read_rec(t2, rec)
assert pak_graft.material_cbuffer(t2, fx["entries"][hcoat][0], len(params)) is not None
print("ok  graft: coat <- ellie jacket (%s), hands <- ellie glove: strict validator clean, effect = donor's under the name remap (%d fields)" % (
    ", ".join("%s %s" % (v, k) for k, v in g.items()), nf))

# ---- the night29 graft (record copied, bindings outside the GEOMETRY_1 array, no EFFECT / VRAM_DESC) is refused
old = snow_clone.Pak(recv)
gr = snow_clone.graft_record(old, snow_clone.Pak(game("ellie-patrol-jacket")), snow_clone.techniques(snow_clone.Pak(game("ellie-patrol-jacket")))["jacket"])
tl = old.ptr(gr[0], gr[1] + 0x20)
bp = old.ptr(tl[0], tl[1] + 24)
gb = pak_graft.geometry(old)["bind"]
assert bp[0] != gb[0] or not (gb[1] <= bp[1] < gb[1] + pak_graft.BIND * pak_graft.geometry(old)["nbind"])
print("ok  night29-style graft_record bindings sit outside the binding array (what +1677091 crashed on)")

# ---- BC7 mode-6 encoder (mp_snow_pak.bc7_blocks: garments whose colour / only free mask slot is BC7) decodes back within 1-2 levels
import numpy as np  # noqa: E402
import mp_snow_pak  # noqa: E402


def _dec6(b):
    v = int.from_bytes(b, "little")
    g = lambda o, n: (v >> o) & ((1 << n) - 1)   # noqa: E731
    assert g(0, 7) == 64
    e0 = np.array([(g(7 + 14 * c, 7) << 1) | g(63, 1) for c in range(4)])
    e1 = np.array([(g(14 + 14 * c, 7) << 1) | g(64, 1) for c in range(4)])
    idx = [g(65, 3)] + [g(68 + 4 * (k - 1), 4) for k in range(1, 16)]
    W = mp_snow_pak.BC7_W
    return np.array([((64 - W[i]) * e0 + W[i] * e1 + 32) >> 6 for i in idx]).reshape(4, 4, 4)


rng = np.random.default_rng(1)
yy, xx = np.mgrid[0:64, 0:64]
img = np.clip(np.stack([xx * 3, yy * 3, (xx + yy) * 2, np.full_like(xx, 255)], -1) + rng.normal(0, 4, (64, 64, 4)), 0, 255).astype(np.uint8)
bl = mp_snow_pak.bc7_blocks(img)
out = np.zeros(img.shape, int)
for k in range(256):
    y, x = divmod(k, 16)
    out[4 * y:4 * y + 4, 4 * x:4 * x + 4] = _dec6(bl[16 * k:16 * k + 16])
err = float(np.sqrt(((out - img.astype(int)) ** 2).mean()))
assert err < 4.0, err
print("ok  BC7 mode-6 encoder: RGBA gradient + noise decodes back at %.2f RMS" % err)

# ---- prop paks: a coat grafted from ellie-patrol-jacket into a cloth-sim prop pak brings cbuffers no stock prop effect uses (orange coat in bind pose in game);
# the prop-safe donor (militia-male-02-jacket-cloth wlf-patch) passes
cloth = game("scar-male-b-jacket-cloth")
assert pak_graft.is_prop_pak(snow_clone.Pak(cloth)) and not pak_graft.is_prop_pak(snow_clone.Pak(game("scar-male-b-jacket-kit")))
assert pak_validate.check(cloth, "cloth") == []
bad = pak_validate.check(snow_clone.clone(cloth, "scar-m-coat-b", "jacket", donor_pak=game("ellie-patrol-jacket")), "cloth-ellie")
assert any("no stock cloth / animprop effect" in b for b in bad), bad[:3]
ok = pak_validate.check(snow_clone.clone(cloth, "scar-m-coat-b", "wlf-patch", donor_pak=game("militia-male-02-jacket-cloth")), "cloth-wlf")
assert ok == [], ok[:3]
print("ok  prop pak: Ellie's jacket graft rejected (%d problems), militia-male-02-jacket-cloth wlf-patch graft clean" % len(bad))
