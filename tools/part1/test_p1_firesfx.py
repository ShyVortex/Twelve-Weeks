"""offline checks of the Bookstore fire sound level (p1_firesfx.py): donor region copy, tree read back, pak loader mirror checks
(python tools/part1/test_p1_firesfx.py; needs the TLOU2 install for the Forest audio donor pak, else skips)"""
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p1_firesfx as X  # noqa: E402
import p1_rsenv  # noqa: E402
import t2pak  # noqa: E402

FIRES = [{"name": "main", "pos": [118.88, 5.26, 272.6]}, {"name": "rear", "pos": [122.93, 0.15, 257.52]}]


def donor_pak():
    import level_edit
    try:
        return open(level_edit.fetch(X.DONOR_LEVEL, os.path.join(tempfile.gettempdir(), "t2r-firesfx-test"), suffixes=("-ingame",))["-ingame"], "rb").read()
    except (OSError, SystemExit):
        return None


def test_pak():
    d = donor_pak()
    if d is None:
        print("skip: no TLOU2 install")
        return
    data, don = X.make_pak(d, FIRES)
    import p1_convert
    f = os.path.join(tempfile.gettempdir(), "t2r-firesfx-test", "fsfx-ingame.pak")
    open(f, "wb").write(data)
    assert p1_convert.loader_check(f) + p1_convert.vram_check(f) + p1_convert.trailer_check(f) == []
    (regs, grid), = p1_rsenv.read_pak_regions(data)
    assert [r["name"] for r in regs] == X.region_names(2) and grid["dims"] == (1, 1, 1)
    pk = t2pak.TPak(data)
    (pg, off), = [(p, o) for n, p, o in pk.items() if n == "REGION_TREE"]
    page = bytes(pk.pages[pg])
    base = off + 8
    for i, fr in enumerate(FIRES):
        r = struct.unpack_from("<Q", page, base + 8 * i)[0]
        blob = page[r:r + len(don.blob)]
        pos = struct.unpack_from("<3f", blob, don.body + X.BODY_POS)
        want = X.fire_pos(fr, don)
        assert all(abs(pos[t] - want[t]) < 1e-3 for t in range(3))
        aux = struct.unpack_from("<Q", blob, 0x40)[0] - r
        assert struct.unpack_from("<QQ", blob, aux) == (X.AUX_TYPE, X.SOUND)
        assert all((pg, r + so) in pk.fix for so in don.slots)
    print("ok: %d bytes, emitters at %s" % (len(data), [tuple(round(x, 2) for x in X.fire_pos(f, don)) for f in FIRES]))


def test_registry():
    m = {"key": "p1-bookstore"}
    assert X.registry(m) == ["level-name t2r-p1-bookstore-fire-sfx", "level-id t2r-p1-bookstore-fire-sfx",
                             "package t2r-p1-bookstore-fire-sfx-ingame", "sound-bank lvl-nor-forest-amb"]


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "maps"))
    test_registry()
    test_pak()
    print("p1_firesfx tests passed")
